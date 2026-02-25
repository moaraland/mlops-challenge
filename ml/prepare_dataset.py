from __future__ import annotations
import os
os.environ.setdefault("WRAPT_DISABLE_EXTENSIONS", "1")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "1")

import argparse
from dataclasses import asdict
from pathlib import Path
from typing import Iterable, Tuple

import tensorflow as tf
import tensorflow_datasets as tfds

from ml.common import PreparedDatasetInfo, ensure_dir, write_json
from ml.tokenizers import download_and_load_tokenizers, vocab_size

try:
    import tensorflow_text  # noqa: F401
except Exception:
    pass


def _int64_feature(values: Iterable[int]) -> tf.train.Feature:
    return tf.train.Feature(int64_list=tf.train.Int64List(value=list(values)))


def _serialize_example(pt_tokens: tf.Tensor, en_tokens: tf.Tensor) -> bytes:
    feature = {
        "pt": _int64_feature(pt_tokens.numpy().tolist()),
        "en": _int64_feature(en_tokens.numpy().tolist()),
    }
    example = tf.train.Example(features=tf.train.Features(feature=feature))
    return example.SerializeToString()


def _parse_example(example_proto: tf.Tensor) -> Tuple[tf.Tensor, tf.Tensor]:
    feature_spec = {
        "pt": tf.io.VarLenFeature(tf.int64),
        "en": tf.io.VarLenFeature(tf.int64),
    }
    parsed = tf.io.parse_single_example(example_proto, feature_spec)
    pt = tf.sparse.to_dense(parsed["pt"])
    en = tf.sparse.to_dense(parsed["en"])
    return pt, en


def write_tfrecord(
    ds_text: tf.data.Dataset,
    tokenizers,
    output_path: Path,
    max_tokens: int,
    max_records: int | None,
    batch_tokenize: int = 1024,
) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    def tokenize_batch(pt, en):
        pt_tok = tokenizers.pt.tokenize(pt)[:, :max_tokens]
        en_tok = tokenizers.en.tokenize(en)[:, :(max_tokens + 1)]
        return pt_tok, en_tok

    ds = ds_text.batch(batch_tokenize).map(tokenize_batch, num_parallel_calls=tf.data.AUTOTUNE)
    ds = ds.unbatch()

    def not_empty(pt_tok, en_tok):
        return tf.logical_and(tf.size(pt_tok) > 2, tf.size(en_tok) > 2)

    ds = ds.filter(not_empty)
    if max_records is not None:
        ds = ds.take(max_records)

    count = 0
    with tf.io.TFRecordWriter(str(output_path)) as w:
        for pt_tok, en_tok in ds:
            w.write(_serialize_example(pt_tok, en_tok))
            count += 1
    return count


def prepare_dataset(
    output_dir: Path,
    max_tokens: int,
    train_records: int,
    val_records: int,
    seed: int,
    dataset_name: str,
) -> PreparedDatasetInfo:
    output_dir = Path(output_dir)
    ensure_dir(output_dir)

    tokenizers_dir = output_dir / "tokenizers"
    tokenizers = download_and_load_tokenizers(tokenizers_dir)

    examples, _ = tfds.load(dataset_name, with_info=True, as_supervised=True, try_gcs=True)
    train_ds = examples["train"]

    # O dataset "para_crawl/enpt" não tem split de validação, então criamos um a partir do treino
    val_ds = train_ds.take(10_000)

    train_ds = train_ds.shuffle(50_000, seed=seed, reshuffle_each_iteration=False)

    train_path = output_dir / "train.tfrecord"
    val_path = output_dir / "val.tfrecord"

    n_train = write_tfrecord(train_ds, tokenizers, train_path, max_tokens, train_records)
    n_val = write_tfrecord(val_ds, tokenizers, val_path, max_tokens, val_records)

    info = PreparedDatasetInfo(
        dataset_name=dataset_name,
        max_tokens=max_tokens,
        train_records=n_train,
        val_records=n_val,
        tokenizer_dir=str(tokenizers_dir / "ted_hrlr_translate_pt_en_converter"),
        pt_vocab_size=vocab_size(tokenizers.pt),
        en_vocab_size=vocab_size(tokenizers.en),
    )
    write_json(output_dir / "prepared_dataset.json", asdict(info))
    return info


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output_dir", required=True, help="Diretório de saída do dataset processado")
    parser.add_argument("--dataset_name", default="para_crawl/enpt", help="Dataset do TFDS")
    parser.add_argument("--max_tokens", type=int, default=64, help="Máximo de tokens por sentença")
    parser.add_argument("--train_records", type=int, default=5000, help="Número de exemplos de treino (subamostra)")
    parser.add_argument("--val_records", type=int, default=500, help="Número de exemplos de validação (subamostra)")
    parser.add_argument("--seed", type=int, default=42, help="Seed de reprodutibilidade")
    args = parser.parse_args()

    info = prepare_dataset(
        output_dir=Path(args.output_dir),
        dataset_name=args.dataset_name,
        max_tokens=args.max_tokens,
        train_records=args.train_records,
        val_records=args.val_records,
        seed=args.seed,
    )

    print(
        f'{{"stage":"prepare_dataset","output_dir":"{Path(args.output_dir).as_posix()}","train_records":{info.train_records},"val_records":{info.val_records}}}'
    )


if __name__ == "__main__":
    main()
