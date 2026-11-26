import pandas as pd
from sklearn.ensemble import IsolationForest

def detect_vehicular_anomalies(df: pd.DataFrame) -> pd.DataFrame:
    """
    Implementación del modelo Isolation Forest de scikit-learn.
    Recibe un DataFrame con las variables 'hora_ingreso', 'permanencia' y 'frecuencia'.
    Retorna únicamente los registros anómalos sin mutar el DataFrame original.
    """
    features = ['hora_ingreso', 'permanencia', 'frecuencia']

    if not all(col in df.columns for col in features):
        raise ValueError(f"El DataFrame no contiene las columnas requeridas: {features}")

    df_res = df.copy()
    if len(df_res) < 5:
        df_res['is_anomaly'] = pd.Series(dtype=int)
        df_res['anomaly_score'] = pd.Series(dtype=float)
        return df_res.iloc[0:0].copy()

    # Extraemos características sanitizando infinitos y nulos
    X = df_res[features].astype(float).replace([float('inf'), float('-inf')], pd.NA).fillna(0.0)

    model = IsolationForest(
        n_estimators=100,
        contamination=0.05,
        random_state=42
    )

    df_res['is_anomaly'] = model.fit_predict(X)
    df_res['anomaly_score'] = model.decision_function(X)

    return df_res[df_res['is_anomaly'] == -1].copy()
