from django.utils import timezone
from datetime import datetime, timedelta
import json
from django.db.models import Avg, StdDev, Max, Min, Count
from ..models import HealthLog, HealthAnalysis, HealthReport, Medication
from django.utils import timezone
from datetime import timedelta
import json
from decimal import Decimal
import numpy as np
from scipy import stats
from carelink.models import HealthLog, HealthReport

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

class HealthAnalyzer:
    def __init__(self, patient):
        self.patient = patient
        # Enhanced normal ranges with age-specific adjustments
        self.AGE_ADJUSTED_RANGES = {
            'adult': {
                'temperature': (36.1, 37.2),
                'pulse_rate': (60, 100),
                'systolic': (90, 120),
                'diastolic': (60, 80),
                'oxygen_level': (95, 100)
            },
            'elderly': {  # 65+
                'temperature': (36.0, 37.3),
                'pulse_rate': (60, 90),
                'systolic': (100, 130),
                'diastolic': (65, 85),
                'oxygen_level': (92, 98)
            }
        }
        
        # Time-based thresholds for trend analysis
        self.TREND_THRESHOLDS = {
            'temperature_change': 0.5,  # Celsius per day
            'pulse_rate_change': 10,    # Beats per day
            'bp_systolic_change': 10,   # mmHg per day
            'bp_diastolic_change': 5,   # mmHg per day
            'oxygen_level_change': 2     # Percentage points per day
        }

    def get_age_adjusted_ranges(self):
        patient_age = (timezone.now().date() - self.patient.date_of_birth).days // 365
        return self.AGE_ADJUSTED_RANGES['elderly'] if patient_age >= 65 else self.AGE_ADJUSTED_RANGES['adult']

    def analyze_health_data(self, days=7):
        recent_logs = HealthLog.objects.filter(
            patient=self.patient,
            timestamp__gte=timezone.now() - timedelta(days=days)
        ).order_by('timestamp')

        if not recent_logs.exists():
            return None

        # Calculate statistical measures
        stats_data, valid_data = self._calculate_statistics(recent_logs)
        
        # Check for invalid readings immediately
        if stats_data.get('invalid_data', {}).get('temperature'):
            # Create analysis with HIGH risk for invalid temperature
            invalid_temps = stats_data['invalid_data']['temperature']
            risk_factors = [{
                'factor': 'Critical: Invalid Temperature Readings Detected',
                'details': f"Found temperature readings outside safe range (35-42°C): {', '.join(f'{t}°C' for t in invalid_temps)}",
                'severity': 'critical'
            }]
            
            recommendations = [
                "URGENT: Verify temperature measurement equipment for accuracy",
                "Retake temperature readings using calibrated equipment",
                "Document any issues with temperature measurement devices",
                "Contact technical support if measurement issues persist",
                "Consider using backup temperature measurement devices"
            ]
            
            return HealthAnalysis.objects.create(
                patient=self.patient,
                analyzed_date=timezone.now(),
                avg_temperature=None,  # Invalid temperature, so set to None
                avg_blood_pressure="N/A",
                avg_pulse_rate=None,
                avg_oxygen_level=None,
                risk_level='HIGH',
                risk_factors=json.dumps(risk_factors, cls=DecimalEncoder),
                recommendations=json.dumps({
                    'recommendations': recommendations,
                    'insights': [],
                    'trends': {},
                    'invalid_data': stats_data.get('invalid_data', {})
                }, cls=DecimalEncoder)
            )
        
        # Continue with normal analysis if no invalid temperatures
        valid_trends = self._analyze_valid_trends(recent_logs, valid_data)
        risk_level, risk_factors = self._calculate_risk_level_and_factors((stats_data, valid_data), valid_trends, recent_logs)
        insights = self._generate_insights(stats_data, valid_trends, risk_factors)
        recommendations = self._generate_recommendations(risk_factors, insights)

        # Only use values from valid_data for the analysis
        avg_blood_pressure = "N/A"
        avg_temp = None
        avg_pulse_rate = None
        avg_oxygen_level = None

        if valid_data['temperature']:
            avg_temp = np.mean(valid_data['temperature'])
            
        if valid_data['blood_pressure']:
            systolic_values = [bp['systolic'] for bp in valid_data['blood_pressure']]
            diastolic_values = [bp['diastolic'] for bp in valid_data['blood_pressure']]
            if systolic_values and diastolic_values:
                avg_blood_pressure = f"{int(np.mean(systolic_values))}/{int(np.mean(diastolic_values))} mmHg"
                
        if valid_data['pulse_rate']:
            avg_pulse_rate = np.mean(valid_data['pulse_rate'])
            
        if valid_data['oxygen_level']:
            avg_oxygen_level = np.mean(valid_data['oxygen_level'])

        analysis = HealthAnalysis.objects.create(
            patient=self.patient,
            analyzed_date=timezone.now(),
            avg_temperature=avg_temp,
            avg_blood_pressure=avg_blood_pressure,
            avg_pulse_rate=avg_pulse_rate,
            avg_oxygen_level=avg_oxygen_level,
            risk_level=risk_level,
            risk_factors=json.dumps(risk_factors, cls=DecimalEncoder),
            recommendations=json.dumps({
                'recommendations': recommendations,
                'insights': insights,
                'trends': valid_trends,
                'invalid_data': stats_data.get('invalid_data', {})
            }, cls=DecimalEncoder)
        )

        return analysis

    def _celsius_to_fahrenheit(self, celsius):
        if celsius is None:
            return None
        return (float(celsius) * 9/5) + 32

    def _validate_temperature(self, temp_c):
        """Validate if temperature is in a reasonable range (35°C to 42°C)"""
        if temp_c is None:
            return False
        try:
            temp = float(temp_c)
            return 35.0 <= temp <= 42.0
        except (ValueError, TypeError):
            return False

    def _calculate_statistics(self, logs):
        stats_data = {}
        
        # First validate and extract valid readings
        valid_data = {
            'temperature': [],
            'pulse_rate': [],
            'oxygen_level': [],
            'blood_pressure': []
        }
        
        invalid_data = {
            'temperature': [],
            'pulse_rate': [],
            'oxygen_level': [],
            'blood_pressure': []
        }
        
        # Process each log entry
        for log in logs:
            # Temperature validation (35-42°C)
            if log.temperature is not None:
                try:
                    temp = float(log.temperature)
                    # Strict temperature validation
                    if 35.0 <= temp <= 42.0:
                        valid_data['temperature'].append(temp)
                    else:
                        # Explicitly add to invalid data
                        invalid_data['temperature'].append(temp)
                except (ValueError, TypeError):
                    # If conversion fails, skip this reading
                    continue
                
            # Validate pulse rate (40-200 BPM)
            if log.pulse_rate is not None:
                if 40 <= log.pulse_rate <= 200:
                    valid_data['pulse_rate'].append(log.pulse_rate)
                else:
                    invalid_data['pulse_rate'].append(log.pulse_rate)
                
            # Validate oxygen level (50-100%)
            if log.oxygen_level is not None:
                if 50 <= log.oxygen_level <= 100:
                    valid_data['oxygen_level'].append(log.oxygen_level)
                else:
                    invalid_data['oxygen_level'].append(log.oxygen_level)
                
            # Validate blood pressure
            if log.blood_pressure and '/' in log.blood_pressure:
                try:
                    systolic, diastolic = map(int, log.blood_pressure.split('/'))
                    if 60 <= systolic <= 200 and 40 <= diastolic <= 120:
                        valid_data['blood_pressure'].append({'systolic': systolic, 'diastolic': diastolic})
                    else:
                        invalid_data['blood_pressure'].append({'systolic': systolic, 'diastolic': diastolic})
                except (ValueError, TypeError):
                    continue

        # Calculate statistics only for valid data
        if valid_data['temperature']:
            stats_data['temperature'] = self._compute_vital_stats(valid_data['temperature'])
            
        if valid_data['pulse_rate']:
            stats_data['pulse_rate'] = self._compute_vital_stats(valid_data['pulse_rate'])
            
        if valid_data['oxygen_level']:
            stats_data['oxygen_level'] = self._compute_vital_stats(valid_data['oxygen_level'])
            
        if valid_data['blood_pressure']:
            systolic_values = [bp['systolic'] for bp in valid_data['blood_pressure']]
            diastolic_values = [bp['diastolic'] for bp in valid_data['blood_pressure']]
            stats_data['systolic'] = self._compute_vital_stats(systolic_values)
            stats_data['diastolic'] = self._compute_vital_stats(diastolic_values)

        # Ensure invalid data is properly included in stats_data
        stats_data['invalid_data'] = invalid_data
        
        return stats_data, valid_data

    def _compute_vital_stats(self, values):
        if not values:
            return None
        
        values = np.array(values)
        return {
            'mean': float(np.mean(values)),
            'median': float(np.median(values)),
            'std': float(np.std(values)) if len(values) > 1 else 0,
            'min': float(np.min(values)),
            'max': float(np.max(values)),
            'range': float(np.ptp(values)),
            'iqr': float(np.percentile(values, 75) - np.percentile(values, 25)),
            'outliers': self._detect_outliers(values)
        }

    def _detect_outliers(self, values):
        if len(values) < 4:  # Need at least 4 points for meaningful outlier detection
            return []
            
        q1 = np.percentile(values, 25)
        q3 = np.percentile(values, 75)
        iqr = q3 - q1
        lower_bound = q1 - (1.5 * iqr)
        upper_bound = q3 + (1.5 * iqr)
        
        return [float(v) for v in values if v < lower_bound or v > upper_bound]

    def _analyze_valid_trends(self, logs, valid_data):
        """Analyze trends using only valid data"""
        trends = {}
        
        # Temperature trends
        if valid_data['temperature']:
            trends['temperature'] = self._calculate_trend(valid_data['temperature'])
            
        # Pulse rate trends
        if valid_data['pulse_rate']:
            trends['pulse_rate'] = self._calculate_trend(valid_data['pulse_rate'])
            
        # Oxygen level trends
        if valid_data['oxygen_level']:
            trends['oxygen_level'] = self._calculate_trend(valid_data['oxygen_level'])
            
        # Blood pressure trends
        if valid_data['blood_pressure']:
            systolic_values = [bp['systolic'] for bp in valid_data['blood_pressure']]
            diastolic_values = [bp['diastolic'] for bp in valid_data['blood_pressure']]
            trends['blood_pressure'] = {
                'systolic': self._calculate_trend(systolic_values),
                'diastolic': self._calculate_trend(diastolic_values)
            }
            
        return trends

    def _calculate_trend(self, values):
        if not values:
            return None

        # Convert to numpy array and create time points
        y = np.array(values)
        x = np.arange(len(y))
        
        # Calculate linear regression
        slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)
        
        # Determine trend direction and magnitude
        direction = 'stable'
        if slope > 0:
            direction = 'increasing'
        elif slope < 0:
            direction = 'decreasing'
            
        # Calculate relative change (as percentage of mean)
        mean_value = np.mean(y)
        relative_change = (slope * len(y)) / mean_value * 100 if mean_value != 0 else 0
        
        return {
            'direction': direction,
            'magnitude': abs(relative_change),
            'slope': slope,
            'r_squared': r_value ** 2,
            'p_value': p_value,
            'significance': 'significant' if p_value < 0.05 else 'not significant'
        }

    def _calculate_risk_level_and_factors(self, stats_data, trends, logs):
        stats_data, valid_data = stats_data  # Unpack the tuple
        risk_factors = []
        risk_score = 0
        
        # Check for invalid readings FIRST
        invalid_readings = self._check_invalid_readings(valid_data, logs)
        
        # If we have ANY invalid readings, immediately set HIGH risk
        if invalid_readings:
            risk_factors.extend(invalid_readings)
            return 'HIGH', risk_factors  # Return immediately with HIGH risk
        
        # Only proceed with other risk assessments if all readings are valid
        if valid_data['temperature']:
            temp_risks = self._assess_temperature_risks(stats_data['temperature'])
            risk_factors.extend(temp_risks['factors'])
            risk_score += temp_risks['score']
        
        if valid_data['blood_pressure']:
            bp_risks = self._assess_blood_pressure_risks(stats_data['systolic'], stats_data['diastolic'])
            risk_factors.extend(bp_risks['factors'])
            risk_score += bp_risks['score']
        
        if valid_data['pulse_rate']:
            pulse_risks = self._assess_pulse_risks(stats_data['pulse_rate'])
            risk_factors.extend(pulse_risks['factors'])
            risk_score += pulse_risks['score']
        
        if valid_data['oxygen_level']:
            oxygen_risks = self._assess_oxygen_risks(stats_data['oxygen_level'])
            risk_factors.extend(oxygen_risks['factors'])
            risk_score += oxygen_risks['score']
        
        # Assess combined risks
        if any(valid_data.values()):
            combined_risks = self._assess_combined_risks(stats_data, risk_factors)
            risk_factors.extend(combined_risks['factors'])
            risk_score += combined_risks['score']
        
        # Assess trends
        if trends:
            trend_risks = self._assess_trends(trends, stats_data)
            risk_factors.extend(trend_risks['factors'])
            risk_score += trend_risks['score']
        
        # Calculate final risk level
        risk_level = self._calculate_final_risk_level(risk_score, risk_factors)
        
        return risk_level, risk_factors

    def _check_invalid_readings(self, valid_data, logs):
        invalid_factors = []
        total_logs = len(logs)
        
        # Get all readings from logs
        all_temps = []
        all_pulses = []
        all_oxygen = []
        
        # Collect all non-None readings
        for log in logs:
            try:
                if log.temperature is not None:
                    temp = float(log.temperature)
                    all_temps.append(temp)
                if log.pulse_rate is not None:
                    all_pulses.append(log.pulse_rate)
                if log.oxygen_level is not None:
                    all_oxygen.append(log.oxygen_level)
            except (ValueError, TypeError):
                continue
        
        # Check temperature readings - STRICT validation
        invalid_temps = [t for t in all_temps if t < 35.0 or t > 42.0]
        if invalid_temps:
            details = [f"{t}°C" for t in invalid_temps]
            invalid_factors.append({
                'factor': 'Critical: Invalid Temperature Readings Detected',
                'details': f"Found temperature readings outside safe range (35-42°C): {', '.join(details)}",
                'severity': 'critical'
            })
        
        # Check pulse rate readings
        invalid_pulses = [p for p in all_pulses if not (40 <= p <= 200)]
        if invalid_pulses:
            invalid_factors.append({
                'factor': 'Critical: Invalid Pulse Rate Readings',
                'details': f"Found pulse readings outside safe range (40-200 BPM): {', '.join(str(p) for p in invalid_pulses)}",
                'severity': 'critical'
            })
        
        # Check oxygen readings
        invalid_oxygen = [o for o in all_oxygen if not (50 <= o <= 100)]
        if invalid_oxygen:
            invalid_factors.append({
                'factor': 'Critical: Invalid Oxygen Readings',
                'details': f"Found oxygen readings outside safe range (50-100%): {', '.join(str(o) for o in invalid_oxygen)}",
                'severity': 'critical'
            })
        
        # Check data reliability
        for vital_name, values in valid_data.items():
            all_readings = all_temps if vital_name == 'temperature' else all_pulses if vital_name == 'pulse_rate' else all_oxygen if vital_name == 'oxygen_level' else []
            if len(values) == 0 and len(all_readings) > 0:
                invalid_factors.append({
                    'factor': f'Critical: All {vital_name.replace("_", " ").title()} Readings Invalid',
                    'details': f"No valid {vital_name.replace('_', ' ')} readings found in {len(all_readings)} measurements.",
                    'severity': 'critical'
                })
        
        return invalid_factors

    def _assess_temperature_risks(self, temp_stats):
        risks = {'factors': [], 'score': 0}
        temp_max = temp_stats['max']
        temp_mean = temp_stats['mean']
        
        if temp_max >= 40.0:  # Hyperpyrexia
            risks['factors'].append({
                'factor': 'Severe Hyperpyrexia',
                'details': f"Dangerously high temperature: {temp_max}°C",
                'severity': 'critical'
            })
            risks['score'] += 5
        elif temp_max >= 39.0:  # High fever
            risks['factors'].append({
                'factor': 'High Fever',
                'details': f"High temperature: {temp_max}°C",
                'severity': 'high'
            })
            risks['score'] += 3
        elif temp_max >= 38.0:  # Fever
            risks['factors'].append({
                'factor': 'Fever',
                'details': f"Elevated temperature: {temp_max}°C",
                'severity': 'moderate'
            })
            risks['score'] += 2
            
        if temp_mean < 36.0:  # Hypothermia
            risks['factors'].append({
                'factor': 'Hypothermia',
                'details': f"Low temperature: {temp_mean}°C",
                'severity': 'high'
            })
            risks['score'] += 3
            
        return risks

    def _assess_blood_pressure_risks(self, sys_stats, dia_stats):
        risks = {'factors': [], 'score': 0}
        sys_mean = sys_stats['mean']
        dia_mean = dia_stats['mean']
        
        # Hypertensive Crisis
        if sys_mean >= 180 or dia_mean >= 120:
            risks['factors'].append({
                'factor': 'Hypertensive Crisis',
                'details': f"Dangerous blood pressure: {int(sys_mean)}/{int(dia_mean)} mmHg",
                'severity': 'critical'
            })
            risks['score'] += 5
        # Stage 2 Hypertension
        elif sys_mean >= 160 or dia_mean >= 100:
            risks['factors'].append({
                'factor': 'Stage 2 Hypertension',
                'details': f"Very high blood pressure: {int(sys_mean)}/{int(dia_mean)} mmHg",
                'severity': 'high'
            })
            risks['score'] += 4
        # Stage 1 Hypertension
        elif sys_mean >= 140 or dia_mean >= 90:
            risks['factors'].append({
                'factor': 'Stage 1 Hypertension',
                'details': f"High blood pressure: {int(sys_mean)}/{int(dia_mean)} mmHg",
                'severity': 'moderate'
            })
            risks['score'] += 2
        # Hypotension
        elif sys_mean < 90 or dia_mean < 60:
            risks['factors'].append({
                'factor': 'Hypotension',
                'details': f"Low blood pressure: {int(sys_mean)}/{int(dia_mean)} mmHg",
                'severity': 'high'
            })
            risks['score'] += 3
            
        return risks

    def _assess_pulse_risks(self, pulse_stats):
        risks = {'factors': [], 'score': 0}
        pulse_mean = pulse_stats['mean']
        
        if pulse_mean > 150:  # Severe tachycardia
            risks['factors'].append({
                'factor': 'Severe Tachycardia',
                'details': f"Dangerous heart rate: {int(pulse_mean)} BPM",
                'severity': 'critical'
            })
            risks['score'] += 5
        elif pulse_mean > 100:  # Tachycardia
            risks['factors'].append({
                'factor': 'Tachycardia',
                'details': f"Elevated heart rate: {int(pulse_mean)} BPM",
                'severity': 'high'
            })
            risks['score'] += 3
        elif pulse_mean < 60:  # Bradycardia
            risks['factors'].append({
                'factor': 'Bradycardia',
                'details': f"Low heart rate: {int(pulse_mean)} BPM",
                'severity': 'high'
            })
            risks['score'] += 3
            
        return risks

    def _assess_oxygen_risks(self, oxygen_stats):
        risks = {'factors': [], 'score': 0}
        oxygen_mean = oxygen_stats['mean']
        
        if oxygen_mean < 90:  # Severe hypoxemia
            risks['factors'].append({
                'factor': 'Severe Hypoxemia',
                'details': f"Dangerously low oxygen: {int(oxygen_mean)}%",
                'severity': 'critical'
            })
            risks['score'] += 5
        elif oxygen_mean < 94:  # Moderate hypoxemia
            risks['factors'].append({
                'factor': 'Moderate Hypoxemia',
                'details': f"Low oxygen level: {int(oxygen_mean)}%",
                'severity': 'high'
            })
            risks['score'] += 3
            
        return risks

    def _assess_combined_risks(self, stats_data, existing_risks):
        risks = {'factors': [], 'score': 0}
        
        # Count abnormal vitals
        abnormal_vitals = 0
        high_severity_count = len([r for r in existing_risks if r['severity'] in ['high', 'critical']])
        
        if high_severity_count >= 2:
            risks['factors'].append({
                'factor': 'Multiple Critical Conditions',
                'details': f"Patient has {high_severity_count} high/critical risk factors",
                'severity': 'critical'
            })
            risks['score'] += 5
        
        # Check for specific combinations
        has_high_temp = any(r['factor'] in ['Severe Hyperpyrexia', 'High Fever'] for r in existing_risks)
        has_high_pulse = any(r['factor'] in ['Severe Tachycardia', 'Tachycardia'] for r in existing_risks)
        has_low_oxygen = any(r['factor'] in ['Severe Hypoxemia', 'Moderate Hypoxemia'] for r in existing_risks)
        
        if has_high_temp and has_high_pulse:
            risks['factors'].append({
                'factor': 'Fever with Tachycardia',
                'details': "Combined fever and elevated heart rate indicates possible infection",
                'severity': 'high'
            })
            risks['score'] += 3
            
        if has_low_oxygen and (has_high_temp or has_high_pulse):
            risks['factors'].append({
                'factor': 'Respiratory Distress',
                'details': "Low oxygen with other vital sign changes indicates possible respiratory issues",
                'severity': 'critical'
            })
            risks['score'] += 5
            
        return risks

    def _assess_trends(self, trends, stats_data):
        risks = {'factors': [], 'score': 0}
        
        for vital, trend in trends.items():
            if trend['significance'] == 'significant':
                if trend['magnitude'] > 10:  # Significant change
                    severity = 'high' if trend['magnitude'] > 20 else 'moderate'
                    risks['factors'].append({
                        'factor': f'Rapid {vital.replace("_", " ").title()} Change',
                        'details': f"Significant {trend['direction']} trend ({trend['magnitude']:.1f}% change)",
                        'severity': severity
                    })
                    risks['score'] += 4 if severity == 'high' else 2
                    
        return risks

    def _calculate_final_risk_level(self, risk_score, risk_factors):
        # Count factors by severity
        critical_count = len([f for f in risk_factors if f['severity'] == 'critical'])
        high_count = len([f for f in risk_factors if f['severity'] == 'high'])
        moderate_count = len([f for f in risk_factors if f['severity'] == 'moderate'])
        
        # HIGH risk conditions:
        # 1. Any critical severity factor
        # 2. Risk score >= 5
        # 3. Three or more high severity factors
        # 4. Five or more total risk factors
        if (critical_count > 0 or 
            risk_score >= 5 or 
            high_count >= 3 or 
            (high_count + moderate_count) >= 5):
            return 'HIGH'
            
        # MODERATE risk conditions:
        # 1. Any high severity factor
        # 2. Risk score >= 3
        # 3. Two or more moderate factors
        elif (high_count > 0 or 
              risk_score >= 3 or 
              moderate_count >= 2):
            return 'MODERATE'
            
        # LOW risk otherwise
        else:
            return 'LOW'

    def _generate_insights(self, stats_data, trends, risk_factors):
        insights = []
        
        # Analyze patterns in vital signs
        self._analyze_vital_patterns(stats_data, insights)
        
        # Analyze trends
        self._analyze_trend_patterns(trends, insights)
        
        # Generate correlation insights
        self._analyze_correlations(stats_data, insights)
        
        return insights

    def _analyze_vital_patterns(self, stats_data, insights):
        for vital, data in stats_data.items():
            if data and 'outliers' in data and data['outliers']:
                insights.append({
                    'type': 'pattern',
                    'vital_sign': vital,
                    'finding': f"Detected {len(data['outliers'])} unusual readings",
                    'details': f"Unusual values: {', '.join(map(str, data['outliers']))}"
                })

    def _analyze_trend_patterns(self, trends, insights):
        for vital, trend in trends.items():
            if vital != 'blood_pressure' and trend['significance'] == 'significant':
                insights.append({
                    'type': 'trend',
                    'vital_sign': vital,
                    'finding': f"Significant {trend['direction']} trend detected",
                    'details': f"{trend['magnitude']:.1f}% change over the period"
                })

    def _analyze_correlations(self, stats_data, insights):
        # Analyze relationships between different vital signs
        vitals = ['temperature', 'pulse_rate', 'systolic', 'diastolic']
        for i in range(len(vitals)):
            for j in range(i + 1, len(vitals)):
                if vitals[i] in stats_data and vitals[j] in stats_data:
                    correlation = self._calculate_correlation(
                        stats_data[vitals[i]],
                        stats_data[vitals[j]]
                    )
                    if abs(correlation) > 0.7:  # Strong correlation threshold
                        insights.append({
                            'type': 'correlation',
                            'vital_signs': [vitals[i], vitals[j]],
                            'finding': f"Strong {'positive' if correlation > 0 else 'negative'} correlation",
                            'details': f"Correlation coefficient: {correlation:.2f}"
                        })

    def _calculate_correlation(self, data1, data2):
        if not (data1 and data2):
            return 0
        try:
            return np.corrcoef(data1['values'], data2['values'])[0, 1]
        except:
            return 0

    def _generate_recommendations(self, risk_factors, insights):
        recommendations = []
        
        # Check for invalid data first
        has_invalid_data = any(factor['factor'].startswith('Critical: Invalid') for factor in risk_factors)
        if has_invalid_data:
            recommendations.extend([
                "URGENT: Verify all measurement equipment for accuracy",
                "Retake all vital signs using calibrated equipment",
                "Document any issues with measurement devices",
                "Contact technical support if measurement issues persist",
                "Consider using backup measurement devices if available"
            ])
            return recommendations  # Return immediately as other recommendations aren't relevant with invalid data
        
        # Continue with normal recommendations if data is valid
        recommendation_map = {
            "Severe Hyperpyrexia": [
                "URGENT: Seek immediate medical attention",
                "Apply cooling measures as directed by healthcare provider",
                "Monitor temperature every 15-30 minutes",
                "Ensure adequate hydration"
            ],
            "High Fever": [
                "Monitor temperature every 4 hours",
                "Ensure adequate hydration",
                "Consider consulting healthcare provider if fever persists"
            ],
            "Elevated Temperature": [
                "Monitor temperature twice daily",
                "Rest and maintain good hydration"
            ],
            "Tachycardia": [
                "Monitor pulse rate more frequently",
                "Avoid caffeine and stimulants",
                "Practice relaxation techniques",
                "Consult healthcare provider if persistent"
            ],
            "Bradycardia": [
                "Monitor pulse rate regularly",
                "Report any dizziness or fatigue",
                "Review current medications with healthcare provider"
            ],
            "Hypertension": [
                "Monitor blood pressure twice daily",
                "Reduce sodium intake",
                "Maintain regular physical activity",
                "Consider stress management techniques"
            ],
            "Hypotension": [
                "Monitor blood pressure regularly",
                "Stay hydrated",
                "Report any dizziness or fainting",
                "Consider increasing salt intake (consult healthcare provider first)"
            ],
            "Significant temperature change": [
                "Monitor temperature closely",
                "Adjust medication or treatment plan as needed"
            ],
            "Significant pulse rate change": [
                "Monitor pulse rate closely",
                "Adjust medication or treatment plan as needed"
            ],
            "Significant blood pressure change": [
                "Monitor blood pressure closely",
                "Adjust medication or treatment plan as needed"
            ],
            "Consistent Blood Pressure Change": [
                "Consult healthcare provider for further evaluation",
                "Adjust medication or treatment plan as needed"
            ]
        }
        
        # Add recommendations based on risk factors
        for factor in risk_factors:
            if factor['factor'] in recommendation_map:
                recommendations.extend(recommendation_map[factor['factor']])
        
        return list(set(recommendations))  # Remove duplicates

    def generate_report(self, report_type):
        if report_type == 'DAILY':
            return self.generate_daily_report()
        elif report_type == 'WEEKLY':
            return self.generate_weekly_report()
        elif report_type == 'MONTHLY':
            return self.generate_monthly_report()
        else:
            raise ValueError("Invalid report type")

    def generate_daily_report(self):
        return self._generate_report_for_period(days=1)

    def generate_weekly_report(self):
        return self._generate_report_for_period(days=7)

    def generate_monthly_report(self):
        return self._generate_report_for_period(days=30)

    def _generate_report_for_period(self, days):
        end_date = timezone.now()
        start_date = end_date - timedelta(days=days)
        health_logs = HealthLog.objects.filter(patient=self.patient, timestamp__range=(start_date, end_date))

        report_data = {
            'temperature': [float(log.temperature) if log.temperature is not None else None for log in health_logs],
            'blood_pressure': [log.blood_pressure for log in health_logs],
            'pulse_rate': [log.pulse_rate for log in health_logs],
            'oxygen_level': [log.oxygen_level for log in health_logs],
            'notes': [log.notes for log in health_logs],
        }

        report = HealthReport.objects.create(
            patient=self.patient,
            report_period=days,
            report_data=json.dumps(report_data, cls=DecimalEncoder),  # Use DecimalEncoder
            report_type=self._get_report_type(days)
        )

        return report

    def _get_report_type(self, days):
        if days == 1:
            return 'DAILY'
        elif days == 7:
            return 'WEEKLY'
        elif days == 30:
            return 'MONTHLY'
        else:
            return 'UNKNOWN'