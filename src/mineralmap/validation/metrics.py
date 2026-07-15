"""Metricas de validacion: matriz de confusion, F1, IoU, ROC/AUC, kappa."""


def confusion_matrix(y_true, y_pred):
    raise NotImplementedError


def f1_score(y_true, y_pred):
    raise NotImplementedError


def iou_score(y_true, y_pred):
    raise NotImplementedError


def roc_auc(y_true, y_score):
    raise NotImplementedError


def cohen_kappa(y_true, y_pred):
    raise NotImplementedError
