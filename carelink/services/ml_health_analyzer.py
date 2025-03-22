import numpy as np
from sklearn.ensemble import RandomForestRegressor, IsolationForest
from sklearn.preprocessing import StandardScaler
import pandas as pd
from datetime import datetime, timedelta
from django.db.models import Avg
from ..models import HealthLog, HealthAnalysis, Patient
import joblib
import os

class MLHealthAnalyzer:
    def __init__(self, patient):
        self.patient = patient
        self.scaler = StandardScaler()
        self.models = {
            'vitals_predictor': None,
            'anomaly_detector': None
        }
        self.initialize_models()

    def initialize_models(self):
        """Initialize or load pre-trained models"""
        try:
            # Try to load existing models
            model_path = 'carelink/ml_models/'
            self.models['vitals_predictor'] = joblib.load(f'{model_path}vitals_predictor_{self.patient.id}.joblib')
            self.models['anomaly_detector'] = joblib.load(f'{model_path}anomaly_detector_{self.patient.id}.joblib')
        except:
            # Create new models if not existing
            self.models['vitals_predictor'] = RandomForestRegressor(n_estimators=100)
            self.models['anomaly_detector'] = IsolationForest(contamination=0.1)

    def prepare_health_data(self, days=30):
        """Prepare patient health data for analysis"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        health_logs = HealthLog.objects.filter(
            patient=self.patient,
            timestamp__range=(start_date, end_date)
        ).order_by('timestamp')

        data = []
        for log in health_logs:
            row = {
                'timestamp': log.timestamp,
                'temperature': log.temperature,
                'systolic_bp': float(log.blood_pressure.split('/')[0]) if log.blood_pressure else None,
                'diastolic_bp': float(log.blood_pressure.split('/')[1]) if log.blood_pressure else None,
                'pulse_rate': log.pulse_rate,
                'oxygen_level': log.oxygen_level,
                'hour_of_day': log.timestamp.hour,
                'day_of_week': log.timestamp.weekday()
            }
            data.append(row)

        return pd.DataFrame(data)

    def train_models(self):
        """Train prediction models on patient's historical data"""
        df = self.prepare_health_data(days=60)  # Use 60 days of data for training
        if len(df) < 10:  # Need minimum data points
            return False

        # Prepare features for training
        features = ['hour_of_day', 'day_of_week', 'temperature', 'systolic_bp', 
                   'diastolic_bp', 'pulse_rate', 'oxygen_level']
        X = df[features].fillna(df[features].mean())
        
        # Train vitals predictor
        self.models['vitals_predictor'].fit(X, df['temperature'])  # Predict temperature as example
        
        # Train anomaly detector
        self.models['anomaly_detector'].fit(X)

        # Save trained models
        model_path = 'carelink/ml_models/'
        os.makedirs(model_path, exist_ok=True)
        joblib.dump(self.models['vitals_predictor'], f'{model_path}vitals_predictor_{self.patient.id}.joblib')
        joblib.dump(self.models['anomaly_detector'], f'{model_path}anomaly_detector_{self.patient.id}.joblib')

        return True

    def predict_next_vitals(self):
        """Predict next vital signs based on historical patterns"""
        df = self.prepare_health_data(days=7)  # Use recent data for prediction
        if len(df) < 5:
            return None

        # Prepare latest data point
        latest_data = df.iloc[-1:][['hour_of_day', 'day_of_week', 'temperature', 
                                  'systolic_bp', 'diastolic_bp', 'pulse_rate', 'oxygen_level']]
        
        # Make predictions
        try:
            predicted_temp = self.models['vitals_predictor'].predict(latest_data)
            return {
                'predicted_temperature': round(float(predicted_temp[0]), 1),
                'confidence_score': round(self.models['vitals_predictor'].score(
                    df[['hour_of_day', 'day_of_week', 'temperature', 'systolic_bp', 
                        'diastolic_bp', 'pulse_rate', 'oxygen_level']], 
                    df['temperature']
                ) * 100, 2)
            }
        except:
            return None

    def detect_anomalies(self):
        """Detect anomalies in patient's vital signs"""
        df = self.prepare_health_data(days=7)
        if len(df) < 5:
            return []

        features = ['temperature', 'systolic_bp', 'diastolic_bp', 'pulse_rate', 'oxygen_level']
        X = df[features].fillna(df[features].mean())
        
        try:
            # -1 for anomalies, 1 for normal observations
            anomalies = self.models['anomaly_detector'].predict(X)
            anomaly_dates = df[anomalies == -1]['timestamp'].tolist()
            return anomaly_dates
        except:
            return []

    def generate_health_insights(self):
        """Generate personalized health insights based on historical data"""
        df = self.prepare_health_data(days=30)
        if len(df) < 5:
            return []

        insights = []
        
        # Analyze temperature patterns
        temp_stats = df['temperature'].agg(['mean', 'std', 'min', 'max'])
        if temp_stats['std'] > 0.5:
            insights.append({
                'type': 'TEMPERATURE_VARIATION',
                'message': f"Temperature variations detected (±{round(temp_stats['std'], 2)}°C)",
                'severity': 'MEDIUM'
            })

        # Analyze blood pressure patterns
        if 'systolic_bp' in df.columns:
            bp_stats = df['systolic_bp'].agg(['mean', 'std'])
            if bp_stats['mean'] > 140:
                insights.append({
                    'type': 'HIGH_BP',
                    'message': "Elevated blood pressure pattern detected",
                    'severity': 'HIGH'
                })

        # Time-based patterns
        df['hour'] = df['timestamp'].dt.hour
        morning_temps = df[df['hour'].between(6, 10)]['temperature'].mean()
        evening_temps = df[df['hour'].between(17, 21)]['temperature'].mean()
        if abs(morning_temps - evening_temps) > 0.5:
            insights.append({
                'type': 'DAILY_PATTERN',
                'message': f"Notable temperature difference between morning and evening ({round(abs(morning_temps - evening_temps), 2)}°C)",
                'severity': 'LOW'
            })

        return insights

    def get_care_recommendations(self):
        """Generate automated care plan recommendations"""
        insights = self.generate_health_insights()
        anomalies = self.detect_anomalies()
        predictions = self.predict_next_vitals()

        recommendations = []

        # Add recommendations based on insights
        for insight in insights:
            if insight['severity'] == 'HIGH':
                recommendations.append({
                    'type': 'URGENT',
                    'message': f"Urgent: {insight['message']}. Schedule medical consultation.",
                    'action_required': True
                })
            elif insight['severity'] == 'MEDIUM':
                recommendations.append({
                    'type': 'MONITOR',
                    'message': f"Monitor: {insight['message']}. Increase monitoring frequency.",
                    'action_required': False
                })

        # Add recommendations based on anomalies
        if anomalies:
            recommendations.append({
                'type': 'ANOMALY',
                'message': "Unusual patterns detected in vital signs. Review recent health logs.",
                'action_required': True
            })

        # Add predictive recommendations
        if predictions and predictions['predicted_temperature'] > 37.5:
            recommendations.append({
                'type': 'PREDICTIVE',
                'message': f"Potential fever predicted (Confidence: {predictions['confidence_score']}%). Prepare fever management protocol.",
                'action_required': False
            })

        return recommendations 