from typing import Callable, Optional, Union
from logging import Logger

import torch
import torch.nn as nn
from torch.utils.data import DataLoader

from tqdm import tqdm
import pandas as pd
import numpy as np
import plotly.express as px

from protein_design.constants import device
from protein_design.data import ProteinData, cycle, to_numpy
from protein_design.evaluator import regression_metrics


logger = Logger("protein_design")


def training_step(
    model: nn.Module, data_generator: Callable, optimizer, scheduler
) -> float:
    """One gradient descent step (model weights are updated)

    Parameters
    ----------
    model
        PyTorch model, instance of nn.Module
    data_generator
        Generator wrapper around a PyTorch DataLoader, see data.cycle()
    optimizer
        PyTorch optimizer, e.g. torch.optim.Adam
    scheduler
        PyTorch scheduler, e.g. torch.optim.lr_scheduler.CyclicLR

    Returns
    -------
        Training loss on a batch of data
    """
    X, y = next(data_generator)

    optimizer.zero_grad()
    loss = model.loss(X, y)

    loss.backward()
    optimizer.step()
    scheduler.step()

    return loss.item()


def validation_step(model: nn.Module, data_generator: Callable) -> float:
    """One validation step (no gradients are computed, model weight are not updated)

    Parameters
    ----------
    model
        PyTorch model, instance of nn.Module
    data_generator
        Generator wrapper around a PyTorch DataLoader, see data.cycle()

    Returns
    -------
        Validation loss on a batch of data
    """
    X, y = next(data_generator)

    with torch.no_grad():
        loss = model.loss(X, y)

    return loss.item()


def train(
    model: nn.Module,
    X_train: Union[np.ndarray, torch.tensor],
    X_test: Union[np.ndarray, torch.tensor],
    save_fname: str,
    y_train: Optional[Union[np.ndarray, torch.tensor]] = None,
    y_test: Optional[Union[np.ndarray, torch.tensor]] = None,
    steps: int = 10000,
    pbar_increment: int = 100,
    batch_size: int = 32,
    optimizer=None,
    scheduler=None,
) -> nn.Module:
    """_summary_

    Parameters
    ----------
    model
        PyTorch model, instance of nn.Module
    X_train
        Training data input variables, e.g. array of one-hot encoded protein sequences
    X_test
        Test data input variables
    save_fname
        File name to save best trained model
    y_train, optional
        Training data output variables, e.g. binding affinity, by default None
    y_test, optional
        Test data output variables, by default None
    steps, optional
        Number of gradient descent steps, by default 10000
    pbar_increment, optional
        Number of steps per progress bar update, by default 100
    batch_size, optional
        Number of data points the model processes per gradient update step, by default 32
    optimizer, optional
        Method for updating the gradient. If not provided, defaults to Adam
    scheduler, optional
        Method for controlling learning rate schedule. If not provided, defaults to CyclicLR
        cycling between 1e-4 and 1e-3 without momentum

    Returns
    -------
        Trained model with the lowest loss on validation data
    """
    if optimizer is None:
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-4)
    if scheduler is None:
        scheduler = torch.optim.lr_scheduler.CyclicLR(
            optimizer, 1e-4, 1e-3, cycle_momentum=False
        )

    if y_train is None:
        train_dataset = ProteinData(X_train, X_train)
        test_dataset = ProteinData(X_test, X_test)
    else:
        train_dataset = ProteinData(X_train, y_train)
        test_dataset = ProteinData(X_test, y_test)

    input_shape = list(X_train.shape)
    input_shape[0] = batch_size
    logger.info(model)
    logger.info(f"Training on {len(train_dataset)} examples")
    logger.info(f"Testing on {len(test_dataset)} examples")
    logger.info(f"Model placed on {device}")
    model.double()
    model = model.to(device)

    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    test_loader = DataLoader(test_dataset, batch_size=batch_size, shuffle=True)

    train_cycle = cycle(train_loader)
    test_cycle = cycle(test_loader)

    train_losses, val_losses = [], []

    best_model = None

    best_val_loss = 1e9
    progress_format = "train loss: {:.6f} val loss: {:.6f}"
    with tqdm(total=steps, desc=progress_format.format(0, 0)) as pbar:
        for i in range(steps):
            train_loss = training_step(model, train_cycle, optimizer, scheduler)
            val_loss = validation_step(model, test_cycle)
            train_losses.append(train_loss)
            val_losses.append(val_loss)
            if val_loss < best_val_loss:
                best_val_loss = val_loss
                torch.save(model.state_dict(), save_fname)
                best_model = model
            if (i + 1) % pbar_increment == 0:
                pbar.set_description(progress_format.format(train_loss, val_loss))
                pbar.update(pbar_increment)

    df_result = pd.DataFrame()
    df_result["steps"] = list(range(steps)) + list(range(steps))
    df_result["loss"] = train_losses + val_losses
    df_result["stage"] = ["train"] * steps + ["val"] * steps
    fig = px.line(df_result, x="steps", y="loss", color="stage")
    fig.show()

    if y_train is not None:
        y_true, y_pred = [], []
        for x, y in test_loader:
            y = to_numpy(y)
            y_true.extend(list(y))
            pred = model(x)
            pred = to_numpy(pred).squeeze()
            y_pred.extend(list(pred))
        regression_metrics(np.array(y_true), np.array(y_pred), plot=True)

    return best_model
