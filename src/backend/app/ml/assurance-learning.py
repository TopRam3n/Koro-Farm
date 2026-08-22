import pandas as pd, numpy as np, joblib
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler

df = pd.read_csv("ml/data/plant_health.csv")
features = [ 'Sunlight', 'Temperature','Humidity','Soil pH', 'Soil Moisture']
X = df[features]
y = df['Health'].values

scaler = StandardScaler().fit(X)
Xs = scaler.transform(X)
model = RandomForestRegressor(n_estimators=200, random_state=0)
model.fit(Xs, y)

joblib.dump({"model":model,"scaler":scaler,"features":features},"ml/models/assurance_model.pkl")
print("Model trained and saved to ml/models/assurance_model.pkl")