from flask import Flask, jsonify
import requests


app = Flask(__name__)


@app.route('/weather')
def get_weather():
    # Default to San Francisco coordinates
    # Try to get user's location from IP address
    try:
        # Use ipinfo.io to get location data based on IP
        ip_response = requests.get('https://ipinfo.io/json')
        if ip_response.status_code == 200:
            location_data = ip_response.json()
            # Extract coordinates from the location data
            # Format is "lat,lon"
            if 'loc' in location_data:
                coords = location_data['loc'].split(',')
                lat = float(coords[0])
                lon = float(coords[1])
    except Exception:
        # If there's any error, we'll use the default coordinates
        pass
    
    # First get the grid points
    points_url = f"https://api.weather.gov/points/{lat},{lon}"
    
    try:
        # Get the grid points
        points_response = requests.get(points_url)
        points_data = points_response.json()
        
        if 'properties' not in points_data:
            return jsonify({'error': 'Could not get grid points'}), 500
            
        forecast_url = points_data['properties']['forecast']
        
        # Get the forecast
        forecast_response = requests.get(forecast_url)
        forecast_data = forecast_response.json()
        
        if 'properties' not in forecast_data:
            return jsonify({'error': 'Could not get forecast'}), 500
            
        # Get today's forecast
        periods = forecast_data['properties']['periods']
        today = [p for p in periods if p['number'] == 1][0]
        
        return jsonify({
            'temperature': today['temperature'],
            'temperatureUnit': today['temperatureUnit'],
            'forecast': today['detailedForecast'],
            'location': points_data['properties']['relativeLocation']['properties']['city']
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(port=5000)