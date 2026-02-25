from __future__ import annotations
import os
os.environ.setdefault("WRAPT_DISABLE_EXTENSIONS", "1")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "1")

import argparse
import json
from dataclasses import asdict
from pathlib import Path

import tensorflow as tf

try:
    import tensorflow_text  # noqa: F401
except Exception:
    pass

from ml.common import PreparedDatasetInfo, ensure_dir, generate_run_id, read_json, sha256_file, utc_now_iso, write_json
from ml.model import Transformer, TransformerConfig, WarmupSchedule


def _parse_example(example_proto: tf.Tensor):
    feature_spec = {
        "pt": tf.io.VarLenFeature(tf.int64),
        "en": tf.io.VarLenFeature(tf.int64),
    }
    parsed = tf.io.parse_single_example(example_proto, feature_spec)
    pt = tf.sparse.to_dense(parsed["pt"])
    en = tf.sparse.to_dense(parsed["en"])
    return pt, en


def build_training_dataset(
    tfrecord_path: str | Path,
    batch_size: int,
    max_tokens: int,
    shuffle: bool,
    seed: int,
) -> tf.data.Dataset:
    tfrecord_path = str(tfrecord_path)
    ds = tf.data.TFRecordDataset(
            [tfrecord_path],
            buffer_size=8 * 1024 * 1024,  # 8MB (ajuste conforme disco/rede)
    ).map(_parse_example, num_parallel_calls=tf.data.AUTOTUNE)

    def trim_and_shift(pt, en):
        pt = pt[:max_tokens]
        en = en[: (max_tokens + 1)]
        en_in = en[:-1]
        en_out = en[1:]
        return (pt, en_in), en_out

    ds = ds.map(trim_and_shift, num_parallel_calls=tf.data.AUTOTUNE)

    if shuffle:
        ds = ds.shuffle(10_000, seed=seed, reshuffle_each_iteration=True)

    ds = ds.padded_batch(
        batch_size,
        padded_shapes=((
            [max_tokens],
            [max_tokens],
        ), [max_tokens]),
        padding_values=((
            tf.constant(0, tf.int64),
            tf.constant(0, tf.int64),
        ), tf.constant(0, tf.int64)),
        drop_remainder=True,
    )
    return ds.prefetch(tf.data.AUTOTUNE)


def masked_loss(y_true: tf.Tensor, y_pred: tf.Tensor) -> tf.Tensor:
    loss_fn = tf.keras.losses.SparseCategoricalCrossentropy(from_logits=True, reduction="none")
    loss = loss_fn(y_true, y_pred)
    mask = tf.cast(tf.not_equal(y_true, 0), tf.float32)
    return tf.reduce_sum(loss * mask) / tf.reduce_sum(mask)


def masked_accuracy(y_true: tf.Tensor, y_pred: tf.Tensor) -> tf.Tensor:
    y_pred_ids = tf.argmax(y_pred, axis=-1, output_type=tf.int64)
    matches = tf.cast(tf.equal(y_true, y_pred_ids), tf.float32)
    mask = tf.cast(tf.not_equal(y_true, 0), tf.float32)
    return tf.reduce_sum(matches * mask) / tf.reduce_sum(mask)


class Translator(tf.Module):
    def __init__(self, tokenizers, transformer: Transformer, max_tokens: int):
        super().__init__()
        self.tokenizers = tokenizers
        self.transformer = transformer
        self.max_tokens = max_tokens

    def __call__(self, sentence: tf.Tensor) -> tf.Tensor:
        if len(sentence.shape) == 0:
            sentence = sentence[tf.newaxis]

        encoder_input = self.tokenizers.pt.tokenize(sentence)[:, : self.max_tokens].to_tensor()

        start_end = self.tokenizers.en.tokenize([""])[0]
        start = start_end[0][tf.newaxis]
        end = start_end[1][tf.newaxis]

        output = tf.TensorArray(dtype=tf.int64, size=0, dynamic_size=True)
        output = output.write(0, start)

        for i in tf.range(self.max_tokens):
            out_tokens = tf.transpose(output.stack())
            logits = self.transformer([encoder_input, out_tokens], training=False)
            logits = logits[:, -1:, :]
            next_id = tf.argmax(logits, axis=-1, output_type=tf.int64)
            output = output.write(i + 1, next_id[0])
            if tf.equal(next_id[0][0], end[0]):
                break

        out_tokens = tf.transpose(output.stack())
        text = self.tokenizers.en.detokenize(out_tokens)[0]
        return text


class ExportTranslator(tf.Module):
    def __init__(self, translator: Translator):
        super().__init__()
        self.translator = translator

    @tf.function(input_signature=[tf.TensorSpec(shape=[], dtype=tf.string)])
    def __call__(self, sentence: tf.Tensor) -> tf.Tensor:
        return self.translator(sentence)


def load_prepared_info(data_dir: Path) -> PreparedDatasetInfo:
    obj = read_json(data_dir / "prepared_dataset.json")
    return PreparedDatasetInfo(**obj)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data_dir", required=True, help="Diretório gerado por prepare_dataset")
    parser.add_argument("--artifacts_dir", required=True, help="Diretório base de artefatos versionados")
    parser.add_argument("--run_id", default="", help="Opcional: run_id. Se vazio, gera automaticamente")
    parser.add_argument("--git_sha", default="unknown", help="Sha do git (pode ser passado pelo CI/CD)")
    parser.add_argument("--threshold", type=float, default=0.30, help="Gate: token_accuracy mínima")
    parser.add_argument("--epochs", type=int, default=10, help="Épocas de treino (padrão reduzido)")
    parser.add_argument("--batch_size", type=int, default=32, help="Tamanho do batch (padrão reduzido)")
    parser.add_argument("--max_tokens", type=int, default=64, help="Deve bater com o prepare_dataset")
    parser.add_argument("--num_layers", type=int, default=4)
    parser.add_argument("--d_model", type=int, default=128)
    parser.add_argument("--num_heads", type=int, default=4)
    parser.add_argument("--dff", type=int, default=512)
    parser.add_argument("--dropout", type=float, default=0.1)
    parser.add_argument("--warmup_steps", type=int, default=4000)
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    prepared = load_prepared_info(data_dir)

    run_id = args.run_id or generate_run_id("nmt")
    artifacts_base = Path(args.artifacts_dir)
    run_dir = ensure_dir(artifacts_base / run_id)
    ckpt_dir = ensure_dir(run_dir / "checkpoints")

    tokenizers_root = data_dir / "tokenizers"
    tokenizers = tf.saved_model.load(str(tokenizers_root / "ted_hrlr_translate_pt_en_converter_extracted/ted_hrlr_translate_pt_en_converter"))

    train_ds = build_training_dataset(data_dir / "train.tfrecord", args.batch_size, args.max_tokens, shuffle=True, seed=42)
    val_ds = build_training_dataset(data_dir / "val.tfrecord", args.batch_size, args.max_tokens, shuffle=False, seed=42)
    steps_per_epoch = max(1, (prepared.train_records + args.batch_size - 1) // args.batch_size)
    validation_steps = max(1, (prepared.val_records + args.batch_size - 1) // args.batch_size)

    train_ds = train_ds.repeat()
    val_ds_fit = val_ds.repeat()

    cfg = TransformerConfig(
        pt_vocab_size=prepared.pt_vocab_size,
        en_vocab_size=prepared.en_vocab_size,
        max_tokens=args.max_tokens,
        num_layers=args.num_layers,
        d_model=args.d_model,
        num_heads=args.num_heads,
        dff=args.dff,
        dropout=args.dropout,
    )

    transformer = Transformer(cfg)
    lr = WarmupSchedule(cfg.d_model, warmup_steps=args.warmup_steps)
    opt = tf.keras.optimizers.Adam(lr, beta_1=0.9, beta_2=0.98, epsilon=1e-9)

    transformer.compile(optimizer=opt, loss=masked_loss, metrics=[masked_accuracy])

    transformer.fit(
        train_ds,
        validation_data=val_ds_fit,
        epochs=args.epochs,
        steps_per_epoch=steps_per_epoch,
        validation_steps=validation_steps,
        callbacks=[
            tf.keras.callbacks.ModelCheckpoint(
                    filepath=str(ckpt_dir / "ckpt.weights.h5"),
                    save_weights_only=True,
                    save_best_only=False,
            )
        ],
    )

    eval_out = transformer.evaluate(val_ds, steps=validation_steps, return_dict=True)
    token_acc = float(eval_out.get("masked_accuracy", 0.0))
    status = "approved" if token_acc >= args.threshold else "rejected"

    translator = Translator(tokenizers, transformer, max_tokens=args.max_tokens)
    export = ExportTranslator(translator)
    export_dir = run_dir / "saved_model"
    tf.saved_model.save(export, str(export_dir))

    metrics = {
        "val_token_accuracy": token_acc,
        "val_loss": float(eval_out.get("loss", 0.0)),
    }
    write_json(run_dir / "metrics.json", metrics)

    metadata = {
        "run_id": run_id,
        "timestamp": utc_now_iso(),
        "status": status,
        "threshold": args.threshold,
        "metric_value": token_acc,
        "git_sha": args.git_sha,
        "prepared_dataset": asdict(prepared),
        "export_dir": str(export_dir),
        "export_sha256": sha256_file(export_dir / "saved_model.pb"),
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "model_config": asdict(cfg),
    }
    metadata_path = run_dir / "metadata.json"
    write_json(metadata_path, metadata)

    summary = {
        "stage": "train",
        "run_id": run_id,
        "status": status,
        "metric_value": token_acc,
        "threshold": args.threshold,
        "metadata_path": str(metadata_path.as_posix()),
        "export_dir": str(export_dir.as_posix()),
    }
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
