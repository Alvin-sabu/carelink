import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor, IsolationForest
from sklearn.preprocessing import StandardScaler
from joblib import dump, load
from datetime import datetime, timedelta
from ..models import HealthLog, MLPrediction, MLInsight, MLRecommendation
import os
import traceback

class HealthMLService:
    def __init__(self):
        print("Initializing HealthMLService...")
        self.scaler = StandardScaler()
        self.predictor = RandomForestRegressor(n_estimators=100, random_state=42)
        self.anomaly_detector = IsolationForest(contamination=0.1, random_state=42)
        
        # Ensure models directory exists
        self.models_dir = os.path.join(os.getcwd(), 'models')
        os.makedirs(self.models_dir, exist_ok=True)
        print(f"Models directory: {self.models_dir}")
        
    def prepare_data(self, health_logs):
        """Convert health logs to features for ML models"""
        try:
            print(f"Preparing data from {len(health_logs)} health logs...")
            data = []
            for log in health_logs:
                # Extract systolic and diastolic from blood_pressure string
                systolic, diastolic = None, None
                if log.blood_pressure:
                    try:
                        systolic, diastolic = map(float, log.blood_pressure.split('/'))
                    except:
                        print(f"Warning: Could not parse blood pressure value: {log.blood_pressure}")
                        continue
                    
                row = {
                    'temperature': float(log.temperature) if log.temperature else None,
                    'pulse_rate': float(log.pulse_rate) if log.pulse_rate else None,
                    'systolic_bp': systolic,
                    'diastolic_bp': diastolic,
                    'oxygen_level': float(log.oxygen_level) if log.oxygen_level else None,
                    'hour': log.timestamp.hour,
                    'day_of_week': log.timestamp.weekday()
                }
                data.append(row)
            
            df = pd.DataFrame(data)
            print(f"Prepared DataFrame with shape: {df.shape}")
            return df
            
        except Exception as e:
            print(f"Error in prepare_data: {str(e)}")
            print(traceback.format_exc())
            return pd.DataFrame()

    def train_models(self, patient_id):
        """Train ML models on patient's health data"""
        try:
            print(f"Training models for patient {patient_id}...")
            health_logs = HealthLog.objects.filter(patient_id=patient_id).order_by('timestamp')
            print(f"Found {len(health_logs)} health logs")
            
            if len(health_logs) < 3:  # Need minimum data points
                print("Not enough health logs to train models")
                return False
                
            df = self.prepare_data(health_logs)
            if df.empty:
                print("No valid data to train models")
                return False
                
            print("Filling missing values...")
            df = df.fillna(df.mean())  # Fill missing values with mean
            
            # Train anomaly detector
            print("Training anomaly detector...")
            self.scaler.fit(df)
            scaled_data = self.scaler.transform(df)
            self.anomaly_detector.fit(scaled_data)
            
            # Train predictor (using temperature as target)
            print("Training predictor...")
            X = df.drop('temperature', axis=1)
            y = df['temperature']
            self.predictor.fit(X, y)
            
            # Save models
            print(f"Saving models to {self.models_dir}...")
            dump(self.scaler, os.path.join(self.models_dir, f'scaler_{patient_id}.joblib'))
            dump(self.anomaly_detector, os.path.join(self.models_dir, f'anomaly_{patient_id}.joblib'))
            dump(self.predictor, os.path.join(self.models_dir, f'predictor_{patient_id}.joblib'))
            print("Models saved successfully")
            return True
            
        except Exception as e:
            print(f"Error training models: {str(e)}")
            print(traceback.format_exc())
            return False

    def load_models(self, patient_id):
        """Load trained models for a patient"""
        try:
            print(f"Loading models for patient {patient_id}...")
            models_dir = 'models'
            self.scaler = load(os.path.join(models_dir, f'scaler_{patient_id}.joblib'))
            self.anomaly_detector = load(os.path.join(models_dir, f'anomaly_{patient_id}.joblib'))
            self.predictor = load(os.path.join(models_dir, f'predictor_{patient_id}.joblib'))
            print("Models loaded successfully")
            return True
        except Exception as e:
            print(f"Error loading models: {str(e)}")
            print(traceback.format_exc())
            return False

    def detect_anomalies(self, health_logs):
        """Detect anomalies in health data"""
        try:
            print("Detecting anomalies...")
            df = self.prepare_data(health_logs)
            df = df.fillna(df.mean())  # Fill missing values with mean
            scaled_data = self.scaler.transform(df)
            predictions = self.anomaly_detector.predict(scaled_data)
            anomalies = [i for i, p in enumerate(predictions) if p == -1]  # Return indices of anomalies
            print(f"Found {len(anomalies)} anomalies")
            return anomalies
        except Exception as e:
            print(f"Error detecting anomalies: {str(e)}")
            print(traceback.format_exc())
            return []

    def generate_predictions(self, patient_id):
        """Generate health predictions for next 24 hours"""
        try:
            print(f"Generating predictions for patient {patient_id}...")
            latest_log = HealthLog.objects.filter(patient_id=patient_id).latest('timestamp')
            predictions = []
            
            # Extract systolic and diastolic from blood_pressure string
            systolic, diastolic = None, None
            if latest_log.blood_pressure:
                try:
                    systolic, diastolic = map(float, latest_log.blood_pressure.split('/'))
                except:
                    print(f"Warning: Could not parse blood pressure value: {latest_log.blood_pressure}")
                    pass
            
            base_features = {
                'pulse_rate': latest_log.pulse_rate,
                'systolic_bp': systolic,
                'diastolic_bp': diastolic,
                'oxygen_level': latest_log.oxygen_level
            }
            
            print("Generating predictions for next 24 hours...")
            # Predict for next 24 hours
            for hour in range(24):
                next_time = latest_log.timestamp + timedelta(hours=hour+1)
                features = base_features.copy()
                features['hour'] = next_time.hour
                features['day_of_week'] = next_time.weekday()
                
                X = pd.DataFrame([features])
                X = X.fillna(X.mean())  # Fill missing values with mean
                predicted_temp = self.predictor.predict(X)[0]
                
                prediction = MLPrediction.objects.create(
                    patient_id=patient_id,
                    predicted_temperature=predicted_temp,
                    prediction_time=next_time
                )
                predictions.append(prediction)
            
            print(f"Generated {len(predictions)} predictions")
            return predictions
            
        except Exception as e:
            print(f"Error generating predictions: {str(e)}")
            print(traceback.format_exc())
            return []

    def generate_insights(self, patient_id):
        """Generate health insights based on recent data"""
        try:
            print(f"Generating insights for patient {patient_id}...")
            recent_logs = HealthLog.objects.filter(
                patient_id=patient_id,
                timestamp__gte=datetime.now() - timedelta(days=7)
            ).order_by('timestamp')
            
            if len(recent_logs) < 3:
                print("Not enough recent logs for insights")
                return []
                
            insights = []
            
            # Detect trends
            temps = [float(log.temperature) for log in recent_logs if log.temperature]
            if temps:
                trend = np.polyfit(range(len(temps)), temps, 1)[0]
                
                if abs(trend) > 0.1:
                    insight = MLInsight.objects.create(
                        patient_id=patient_id,
                        insight_type='TREND',
                        description=f'{"Increasing" if trend > 0 else "Decreasing"} temperature trend detected over past week',
                        confidence=min(abs(trend) * 100, 95)
                    )
                    insights.append(insight)
                
            # Check for anomalies
            anomaly_indices = self.detect_anomalies(recent_logs)
            if anomaly_indices:
                insight = MLInsight.objects.create(
                    patient_id=patient_id,
                    insight_type='ANOMALY',
                    description=f'Detected {len(anomaly_indices)} anomalous readings in recent health data',
                    confidence=90
                )
                insights.append(insight)
            
            print(f"Generated {len(insights)} insights")
            return insights
            
        except Exception as e:
            print(f"Error generating insights: {str(e)}")
            print(traceback.format_exc())
            return []

    def generate_recommendations(self, patient_id):
        """Generate care recommendations based on insights and predictions"""
        try:
            print(f"Generating recommendations for patient {patient_id}...")
            recent_insights = MLInsight.objects.filter(
                patient_id=patient_id,
                created_at__gte=datetime.now() - timedelta(days=1)
            )
            
            recommendations = []
            
            for insight in recent_insights:
                if insight.insight_type == 'TREND' and 'Increasing temperature' in insight.description:
                    rec = MLRecommendation.objects.create(
                        patient_id=patient_id,
                        recommendation_type='CARE',
                        description='Consider scheduling a check-up due to increasing temperature trend',
                        priority='MEDIUM',
                        based_on_insight=insight
                    )
                    recommendations.append(rec)
                    
                elif insight.insight_type == 'ANOMALY':
                    rec = MLRecommendation.objects.create(
                        patient_id=patient_id,
                        recommendation_type='ALERT',
                        description='Review recent anomalous health readings with healthcare provider',
                        priority='HIGH',
                        based_on_insight=insight
                    )
                    recommendations.append(rec)
            
            print(f"Generated {len(recommendations)} recommendations")
            return recommendations
            
        except Exception as e:
            print(f"Error generating recommendations: {str(e)}")
            print(traceback.format_exc())
            return [] 