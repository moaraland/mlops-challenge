from __future__ import annotations
import os
os.environ.setdefault("WRAPT_DISABLE_EXTENSIONS", "1")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "1")

from dataclasses import dataclass
from typing import Optional

import tensorflow as tf


def _positional_encoding(length: int, depth: int) -> tf.Tensor:
    depth = depth // 2
    positions = tf.range(length)[:, tf.newaxis]
    depths = tf.range(depth, dtype=tf.float32)[tf.newaxis, :] / tf.cast(depth, tf.float32)
    angle_rates = 1.0 / (10000 ** depths)
    angle_rads = tf.cast(positions, tf.float32) * angle_rates
    pos_encoding = tf.concat([tf.sin(angle_rads), tf.cos(angle_rads)], axis=-1)
    return pos_encoding[tf.newaxis, :, :]


class PositionalEmbedding(tf.keras.layers.Layer):
    def __init__(self, vocab_size: int, d_model: int, max_len: int, **kwargs):
        super().__init__(**kwargs)
        self.d_model = d_model
        self.embedding = tf.keras.layers.Embedding(vocab_size, d_model, mask_zero=True)
        self.pos_encoding = _positional_encoding(max_len, d_model)

    def call(self, x: tf.Tensor) -> tf.Tensor:
        length = tf.shape(x)[1]
        x = self.embedding(x)
        x *= tf.math.sqrt(tf.cast(self.d_model, tf.float32))
        return x + self.pos_encoding[:, :length, :]

    def compute_mask(self, inputs, mask=None):
        return self.embedding.compute_mask(inputs)


def _padding_mask(x: tf.Tensor) -> tf.Tensor:
    return tf.not_equal(x, 0)


def _causal_mask(length: tf.Tensor) -> tf.Tensor:
    i = tf.range(length)[:, None]
    j = tf.range(length)[None, :]
    return i >= j


class EncoderLayer(tf.keras.layers.Layer):
    def __init__(self, d_model: int, num_heads: int, dff: int, dropout: float, **kwargs):
        super().__init__(**kwargs)
        self.mha = tf.keras.layers.MultiHeadAttention(
            num_heads=num_heads,
            key_dim=d_model // num_heads,
            dropout=dropout,
        )
        self.ffn = tf.keras.Sequential([
            tf.keras.layers.Dense(dff, activation="relu"),
            tf.keras.layers.Dense(d_model),
        ])
        self.norm1 = tf.keras.layers.LayerNormalization(epsilon=1e-6)
        self.norm2 = tf.keras.layers.LayerNormalization(epsilon=1e-6)
        self.drop1 = tf.keras.layers.Dropout(dropout)
        self.drop2 = tf.keras.layers.Dropout(dropout)

    def call(self, x: tf.Tensor, training: bool, mask: Optional[tf.Tensor]) -> tf.Tensor:
        attn = self.mha(x, x, x, attention_mask=mask, training=training)
        x = self.norm1(x + self.drop1(attn, training=training))
        ffn = self.ffn(x, training=training)
        x = self.norm2(x + self.drop2(ffn, training=training))
        return x


class DecoderLayer(tf.keras.layers.Layer):
    def __init__(self, d_model: int, num_heads: int, dff: int, dropout: float, **kwargs):
        super().__init__(**kwargs)
        self.self_mha = tf.keras.layers.MultiHeadAttention(
            num_heads=num_heads,
            key_dim=d_model // num_heads,
            dropout=dropout,
        )
        self.cross_mha = tf.keras.layers.MultiHeadAttention(
            num_heads=num_heads,
            key_dim=d_model // num_heads,
            dropout=dropout,
        )
        self.ffn = tf.keras.Sequential([
            tf.keras.layers.Dense(dff, activation="relu"),
            tf.keras.layers.Dense(d_model),
        ])
        self.norm1 = tf.keras.layers.LayerNormalization(epsilon=1e-6)
        self.norm2 = tf.keras.layers.LayerNormalization(epsilon=1e-6)
        self.norm3 = tf.keras.layers.LayerNormalization(epsilon=1e-6)
        self.drop1 = tf.keras.layers.Dropout(dropout)
        self.drop2 = tf.keras.layers.Dropout(dropout)
        self.drop3 = tf.keras.layers.Dropout(dropout)

    def call(
        self,
        x: tf.Tensor,
        enc_out: tf.Tensor,
        training: bool,
        self_mask: Optional[tf.Tensor],
        cross_mask: Optional[tf.Tensor],
    ) -> tf.Tensor:
        attn1 = self.self_mha(x, x, x, attention_mask=self_mask, training=training)
        x = self.norm1(x + self.drop1(attn1, training=training))

        attn2 = self.cross_mha(x, enc_out, enc_out, attention_mask=cross_mask, training=training)
        x = self.norm2(x + self.drop2(attn2, training=training))

        ffn = self.ffn(x, training=training)
        x = self.norm3(x + self.drop3(ffn, training=training))
        return x


@dataclass(frozen=True)
class TransformerConfig:
    pt_vocab_size: int
    en_vocab_size: int
    max_tokens: int
    num_layers: int = 4
    d_model: int = 128
    num_heads: int = 4
    dff: int = 512
    dropout: float = 0.1


class Transformer(tf.keras.Model):
    def __init__(self, cfg: TransformerConfig, **kwargs):
        super().__init__(**kwargs)
        self.cfg = cfg
        self.pt_embed = PositionalEmbedding(cfg.pt_vocab_size, cfg.d_model, cfg.max_tokens, name="pt_embed")
        self.en_embed = PositionalEmbedding(cfg.en_vocab_size, cfg.d_model, cfg.max_tokens, name="en_embed")

        self.enc_layers = [
            EncoderLayer(cfg.d_model, cfg.num_heads, cfg.dff, cfg.dropout, name=f"enc_{i}")
            for i in range(cfg.num_layers)
        ]
        self.dec_layers = [
            DecoderLayer(cfg.d_model, cfg.num_heads, cfg.dff, cfg.dropout, name=f"dec_{i}")
            for i in range(cfg.num_layers)
        ]

        self.final_dense = tf.keras.layers.Dense(cfg.en_vocab_size, name="logits")

    def call(self, inputs, training: bool = False) -> tf.Tensor:
        pt, en_in = inputs

        pt_mask = _padding_mask(pt)
        en_mask = _padding_mask(en_in)

        x = self.pt_embed(pt)
        enc_attn_mask = pt_mask[:, tf.newaxis, :]
        for layer in self.enc_layers:
            x = layer(x, training=training, mask=enc_attn_mask)
        enc_out = x

        L = tf.shape(en_in)[1]
        causal = _causal_mask(L)
        self_attn_mask = tf.logical_and(causal[tf.newaxis, :, :], en_mask[:, tf.newaxis, :])
        cross_mask = pt_mask[:, tf.newaxis, :]

        y = self.en_embed(en_in)
        for layer in self.dec_layers:
            y = layer(y, enc_out, training=training, self_mask=self_attn_mask, cross_mask=cross_mask)

        return self.final_dense(y)


class WarmupSchedule(tf.keras.optimizers.schedules.LearningRateSchedule):
    def __init__(self, d_model: int, warmup_steps: int = 4000):
        super().__init__()
        self.d_model = tf.cast(d_model, tf.float32)
        self.warmup_steps = warmup_steps

    def __call__(self, step: tf.Tensor) -> tf.Tensor:
        step = tf.cast(step, tf.float32)
        arg1 = tf.math.rsqrt(step)
        arg2 = step * (self.warmup_steps ** -1.5)
        return tf.math.rsqrt(self.d_model) * tf.math.minimum(arg1, arg2)
