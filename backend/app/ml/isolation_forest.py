import pandas as pd
from sklearn.ensemble import IsolationForest

def detect_vehicular_anomalies(df: pd.DataFrame) -> pd.DataFrame:
    """
    Implementación del modelo Isolation Forest de scikit-learn.
    Recibe un DataFrame con las variables 'hora_ingreso', 'permanencia' y 'frecuencia'.
    Retorna únicamente los registros anómalos.
    """
    features = ['hora_ingreso', 'permanencia', 'frecuencia']
    
    if not all(col in df.columns for col in features):
        raise ValueError(f"El DataFrame no contiene las columnas requeridas: {features}")
        
    # Extraemos características y rellenamos nulos si existieran
    X = df[features].copy()
    X = X.fillna(0)
    
    # Inicialización del modelo (5% de contaminación esperada)
    model = IsolationForest(
        n_estimators=100,
        contamination=0.05,
        random_state=42
    )
    
    # Predicción: 1 para inliers, -1 para outliers
    df['is_anomaly'] = model.fit_predict(X)
    df['anomaly_score'] = model.decision_function(X)
    
    # Retornamos solo las anomalías detectadas
    anomalies = df[df['is_anomaly'] == -1]
    
    return anomalies
