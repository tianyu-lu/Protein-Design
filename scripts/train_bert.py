import torch
from torch.optim import Adam
from protein_design.learning import WarmupAnnealLR
from protein_design.splitter import random_split
from protein_design.trainer import train
from protein_design.generative import BERT
from protein_design.sequence import (
    seqs_to_integer,
    read_fasta,
    write_fasta,
)
from protein_design.splitter import random_split

fp = "../data/unaligned.fasta"
seqs = read_fasta(fp)

X = seqs_to_integer(seqs)

X = torch.from_numpy(X).type(torch.LongTensor)

X_train, X_test = random_split(X)


train_params = {
    "batch_size": 32,
    "lr": 0.0005,
    "weight_decay": 0.0,
    "warmup_steps": 100,
    "steps": 1000,
}
model_params = {
    "n_head": 2,
    "d_model": 128,
    "d_k": 128,
    "d_v": 128,
    "dropout": 0.1,
    "num_mask": 9,
}

model = BERT(**model_params)

optimizer = Adam(
    model.parameters(), lr=train_params["lr"], weight_decay=train_params["weight_decay"]
)

scheduler = WarmupAnnealLR(optimizer, warmup_steps=train_params["warmup_steps"])

train(
    model,
    X_train,
    X_test,
    "bert.pt",
    batch_size=train_params["batch_size"],
    optimizer=optimizer,
    scheduler=scheduler,
    steps=train_params["steps"],
    pbar_increment=10,
)

seq = "VQLQESGGGLVQAGGSLRLSCAASGSISRFNAMGWWRQAPGKEREFVARIVKGFDPVLADSVKGRFTISIDSAENTLALQMNRLKPEDTAVYYCXXXXXXXXWGQGTQVTVSS"
sampled_seqs = model.sample(seq, n_samples=1000, rm_aa="C,K")

write_fasta("bert.fasta", sampled_seqs)