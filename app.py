import re
from typing import Optional, List, Dict, Any
import json
from flask import Flask, render_template, request, jsonify
import requests
from datetime import datetime
import random

##Rule-based system for translating natural language to FIWARE-QL queries with location awareness
class SimpleFIWARERuleBasedTranslator:
    def __init__(self):
        # Traffic-related keywords 
        self.entity_keywords = {
            'traffic': 'Traffic',
            'road': 'Traffic',
            'street': 'Traffic',
            'vehicle': 'Traffic',
            'vehicles': 'Traffic',
            'car': 'Traffic',
            'cars': 'Traffic',
            'automobile': 'Traffic',
            'cyclist': 'Traffic',
            'cyclists': 'Traffic',
            'bike': 'Traffic',
            'bikes': 'Traffic',
            'bicycle': 'Traffic',
            'bicycles': 'Traffic',
            'biking': 'Traffic',
            'cycling': 'Traffic',
            'pedestrian': 'Traffic',
            'pedestrians': 'Traffic',
            'walking': 'Traffic',
            'walker': 'Traffic',
            'walkers': 'Traffic',
            'footpath': 'Traffic',
            'sidewalk': 'Traffic',
            'crosswalk': 'Traffic',
            'crossing': 'Traffic',
            'speed': 'Traffic',
            'velocity': 'Traffic',
            'mph': 'Traffic',
            'kmh': 'Traffic',
            'kph': 'Traffic',
            'fast': 'Traffic',
            'slow': 'Traffic',
            'intersection': 'Traffic',
            'junction': 'Traffic',
            'roundabout': 'Traffic',
            'crossroads': 'Traffic',
            'transportation': 'Traffic',
            'mobility': 'Traffic',
            'commute': 'Traffic',
            'commuting': 'Traffic',
            'flow': 'Traffic',
            'congestion': 'Traffic',
            'jam': 'Traffic',
            'gridlock': 'Traffic',
            'bottleneck': 'Traffic',
            'rush hour': 'Traffic',
            'transit': 'Traffic',
            'movement': 'Traffic',
            'circulation': 'Traffic',
            'pathway': 'Traffic',
            'route': 'Traffic',
            'motorist': 'Traffic',
            'driver': 'Traffic',
            'driving': 'Traffic',
            
            # Weather-related keywords
            'weather': 'WeatherObserved',
            'temperature': 'WeatherObserved',
            'temp': 'WeatherObserved',
            'celsius': 'WeatherObserved',
            'fahrenheit': 'WeatherObserved',
            'degrees': 'WeatherObserved',
            'hot': 'WeatherObserved',
            'cold': 'WeatherObserved',
            'warm': 'WeatherObserved',
            'cool': 'WeatherObserved',
            'chilly': 'WeatherObserved',
            'freezing': 'WeatherObserved',
            'boiling': 'WeatherObserved',
            'scorching': 'WeatherObserved',
            'sweltering': 'WeatherObserved',
            'frigid': 'WeatherObserved',
            'mild': 'WeatherObserved',
            'moderate': 'WeatherObserved',
            'pleasant': 'WeatherObserved',
            'comfortable': 'WeatherObserved',
            'humidity': 'WeatherObserved',
            'humid': 'WeatherObserved',
            'moisture': 'WeatherObserved',
            'dampness': 'WeatherObserved',
            'dry': 'WeatherObserved',
            'arid': 'WeatherObserved',
            'muggy': 'WeatherObserved',
            'sticky': 'WeatherObserved',
            'clammy': 'WeatherObserved',
            'damp': 'WeatherObserved',
            'moist': 'WeatherObserved',
            'pressure': 'WeatherObserved',
            'barometric': 'WeatherObserved',
            'atmospheric': 'WeatherObserved',
            'climate': 'WeatherObserved',
            'conditions': 'WeatherObserved',
            'forecast': 'WeatherObserved',
            'meteorology': 'WeatherObserved',
            'outdoor': 'WeatherObserved',
            'outside': 'WeatherObserved',
            'air quality': 'WeatherObserved',
            'atmosphere': 'WeatherObserved',
            'environmental': 'WeatherObserved',
            'seasonal': 'WeatherObserved',
            'thermal': 'WeatherObserved',
            
            # Parking-related keywords 
            'parking': 'ParkingSpot',
            'park': 'ParkingSpot',
            'space': 'ParkingSpot',
            'spaces': 'ParkingSpot',
            'spot': 'ParkingSpot',
            'spots': 'ParkingSpot',
            'lot': 'ParkingSpot',
            'garage': 'ParkingSpot',
            'carpark': 'ParkingSpot',
            'car park': 'ParkingSpot',
            'parking lot': 'ParkingSpot',
            'parking garage': 'ParkingSpot',
            'parking space': 'ParkingSpot',
            'parking spot': 'ParkingSpot',
            'bay': 'ParkingSpot',
            'bays': 'ParkingSpot',
            'stall': 'ParkingSpot',
            'stalls': 'ParkingSpot',
            'slot': 'ParkingSpot',
            'slots': 'ParkingSpot',
            'vacancy': 'ParkingSpot',
            'vacancies': 'ParkingSpot',
            'availability': 'ParkingSpot',
            'capacity': 'ParkingSpot',
            'occupancy': 'ParkingSpot',
            'reserved': 'ParkingSpot',
            'handicapped': 'ParkingSpot',
            'disabled': 'ParkingSpot',
            'visitor': 'ParkingSpot',
            'guest': 'ParkingSpot',
            'permit': 'ParkingSpot',
            'zone': 'ParkingSpot',
            'meter': 'ParkingSpot',
            'valet': 'ParkingSpot',
            'underground': 'ParkingSpot',
            'covered': 'ParkingSpot',
            'open-air': 'ParkingSpot',
            'surface': 'ParkingSpot',
            'multi-story': 'ParkingSpot',
            'structure': 'ParkingSpot'
        }
        
        #location mappings for specific locations
        self.location_mappings = {
            #Parking-specific locations
            'scienceharbor': 'ScienceHarbor',
            'science harbor': 'ScienceHarbor',
            'harbor': 'ScienceHarbor',
            
            #Weather-specific locations  
            'sciencehub': 'ScienceHub',
            'science hub': 'ScienceHub',
            'hub': 'ScienceHub',
            
            #Shared locations (both parking and weather)
            'facultycs': 'FacultyCS',
            'faculty cs': 'FacultyCS',
            'faculty': 'FacultyCS',
            'cs': 'FacultyCS',
            'computer science': 'FacultyCS',
            'northpark': 'NorthPark',
            'north park': 'NorthPark',
            'north': 'NorthPark',
            
            #Weather-only locations
            'unimensa': 'UniMensa',
            'uni mensa': 'UniMensa',
            'mensa': 'UniMensa',
            'cafeteria': 'UniMensa',
            'library': 'Library',
            'lib': 'Library',
            'welcomecenter': 'WelcomeCenter',
            'welcome center': 'WelcomeCenter',
            'welcome': 'WelcomeCenter',
            'center': 'WelcomeCenter',
            'geschwisterpark': 'GeschwisterPark',
            'geschwister park': 'GeschwisterPark',
            'geschwister': 'GeschwisterPark'
        }
        
        #Context-specific mappings for ambiguous terms
        self.context_mappings = {
            'science': {
                'parking': 'ScienceHarbor',
                'weather': 'ScienceHub',
                'traffic': 'ScienceHub'
            },
            'science harbor': {
                'weather': 'ScienceHub'
            },
            'science hub': {
                'traffic': 'ScienceHub',
                'weather': 'ScienceHub'
            }
        }

    def extract_location_from_query(self, query: str) -> Optional[str]:
        """Extract specific location mentioned in the query with context awareness"""
        query_lower = query.lower().strip()
        
        #First, determine the entity type for context
        entity_type = self.detect_entity_type(query)
        entity_context = None
        if entity_type == 'ParkingSpot':
            entity_context = 'parking'
        elif entity_type == 'WeatherObserved':
            entity_context = 'weather'
        
        #Look for location keywords - sort by length to match longer phrases first
        sorted_locations = sorted(self.location_mappings.items(), key=lambda x: len(x[0]), reverse=True)
        
        for keyword, location in sorted_locations:
            if keyword in query_lower:
                # Extra check to avoid false matches
                if keyword == 'north' and ('northpark' in query_lower or 'north park' in query_lower):
                    continue  # Let the longer phrases match first
                print(f"DEBUG: Found location keyword '{keyword}' -> '{location}' in query: '{query}'")
                return location
        
        #Check context-specific mappings for ambiguous terms
        if entity_context:
            for ambiguous_term, context_map in self.context_mappings.items():
                if ambiguous_term in query_lower and entity_context in context_map:
                    resolved_location = context_map[entity_context]
                    print(f"DEBUG: Context-resolved '{ambiguous_term}' -> '{resolved_location}' for {entity_context} in query: '{query}'")
                    return resolved_location
        
        print(f"DEBUG: No location found in query: '{query}'")
        return None

    ##entity type detection based on keyword matching
    def detect_entity_type(self, query: str) -> str:
        query_lower = query.lower()
        #count matches for each entity type
        entity_scores = {'Traffic': 0, 'WeatherObserved': 0, 'ParkingSpot': 0}
        for keyword, entity_type in self.entity_keywords.items():
            if keyword in query_lower:
                entity_scores[entity_type] += 1
        #return the entity type with the highest score, can not get two entities at the same time for current version 
        best_entity = max(entity_scores.items(), key=lambda x: x[1])
        
        #if no keywords matched, return a fallback message
        if best_entity[1] == 0:
            return None
        
        return best_entity[0]
        
    #returns entity query with idPattern for location-specific queries
    def translate(self, natural_query: str) -> str:
        query = natural_query.strip()
        if not query:
            return '/entities'
        
        #Detect entity type
        entity_type = self.detect_entity_type(query)
        if not entity_type:
            return '/entities'
        
        #Check for specific location
        specific_location = self.extract_location_from_query(query)
        
        if specific_location:
            # Use idPattern to query for specific location
            return f'/entities?idPattern=.*{specific_location}.*&type={entity_type}'
        else:
            # Query for all entities of this type
            return f'/entities?type={entity_type}'

##Rule based templates for real time json data with enhanced location-specific responses
class RuleBasedResponseGenerator:
    def __init__(self):
        #Templates for Weather 
        self.weather_templates = [
            {
                'intro': [
                    " Let me walk you through what's happening outside.",
                    "Sure, here's what the weather is looking like right now!",
                    "Here's the latest weather data for you.",
                    "Weather check complete!",
                    "Let me break down the current conditions for you."
                ],
                'location': [
                    "In {location}, the temperature is currently {temp}°C. The humidity is at {humidity}%.",
                    "The weather station in {location} is recording {temp}°C with humidity levels at {humidity}%.",
                    "📍 {location} shows a temperature reading of {temp}°C and humidity at {humidity}%. These measurements reflect the current atmospheric conditions.",
                    "Current conditions in {location} are {temp}°C with {humidity}% humidity.",
                    "The data from {location} shows {temp}°C for temperature and {humidity}% for humidity."
                ],
                'summary': [
                    "Looking at all the locations together, I'm calculating an average temperature of {avg_temp}°C. This gives us a nice overview of the general temperature trend across the region.",
                    "When I crunch the numbers from all areas, the average comes out to {avg_temp}°C. This helps us understand the broader weather pattern affecting the entire area.",
                    "📈 The mathematical average across all monitored locations works out to {avg_temp}°C. This average is useful for comparing today's conditions to historical norms.",
                    "Averaging all the temperature readings, we get {avg_temp}°C. This regional average helps paint a picture of whether we're having a warmer or cooler day than usual.",
                    "The mean temperature calculation shows {avg_temp}°C across all stations. This consolidated view helps us understand if there are any significant temperature variations between different areas."
                ],
                'outro': [
                    "What else would you like to know about the weather?",
                    "Is there anything more you'd like to know?",
                    "What would you like to know more about?",
                    "Any other weather information you need?",
                    "What else can I help you with?"
                ]
            },
            {
                'intro': [
                    "I've analyzed the current conditions.",
                    "Let me paint you a picture of today's weather..",
                    "Here's what the data is telling us about your local weather story."
                ],
                'location': [
                    "🌡️ The weather station in {location} is reporting {temp}°C with humidity at {humidity}%. This humidity percentage indicates the amount of water vapor currently in the atmosphere.",
                    "{location} is recording a temperature of {temp}°C. The humidity reading of {humidity}% shows how much moisture the air contains.",
                    "From {location}, the current readings are {temp}°C for temperature with {humidity}% relative humidity. This humidity measurement reflects the moisture content in the air."
                ],
                'summary': [
                    "📊 When I analyze the temperature data from all monitoring points, the average settles at {avg_temp}°C. This regional average helps us understand whether we're experiencing typical conditions for this time of year.",
                    "The computational average across all locations gives us {avg_temp}°C."
                ],
                'outro': [
                    "What else would you like to know?",
                    "Is there anything more about the weather you'd like to know?",
                    "What would you like to know more about?"
                ]
            },
            {
                'intro': [
                    "🌦️ I've processed the latest atmospheric data..",
                    "🌍 Let me walk you through what's happening in the atmosphere..",
                    "⚡ Fresh weather intelligence coming through!"
                ],
                'location': [
                    "The monitoring station in {location} reports a temperature of {temp}°C. The humidity measurement is {humidity}%, which represents the amount of water vapor present in the atmosphere.",
                    "Current data from {location} shows {temp}°C with atmospheric humidity at {humidity}%. This humidity reading indicates the moisture content in the air.",
                    "Weather readings from {location} indicate {temp}°C for temperature and {humidity}% for relative humidity. These measurements show the current atmospheric conditions."
                ],
                'summary': [
                    "Statistical analysis of temperature readings yields an average of {avg_temp}°C across all monitoring stations..",
                    "The aggregated temperature data produces a mean value of {avg_temp}°C."
                ],
                'outro': [
                    "What else would you like to know?",
                    "Is there anything more you need to know?",
                    "What would you like to know more about?"
                ]
            }
        ]
        #Templates for parking responses
        self.parking_templates = [
            {
                'intro': [
                    "I've checked the current parking availability for you.",
                    "Let me give you an update on the parking spaces available.",
                    "Here's the current status of parking spots in your area.",
                    "I've pulled the latest parking information for you. ",
                    "Parking availability update is ready."
                ],
                'location': [
                    "At {location}, there are currently {free} parking spaces available out of a total capacity of {total} spots. This means the facility is operating at {percent}% availability right now.",
                    "The parking facility at {location} shows {free} free spaces available. With a total capacity of {total} spots, this location has {percent}% of its spaces currently open.",
                    "📍 {location} has {free} parking spots free at the moment. The total parking capacity here is {total} spaces, so you're looking at {percent}% availability.",
                    "Current data from {location} indicates {free} available parking spaces. This facility can accommodate {total} vehicles total, meaning {percent}% of the spaces are currently unoccupied.",
                    "The parking sensors at {location} are reporting {free} empty spaces out of {total} total spots. This translates to {percent}% availability at this location."
                ],
                'summary': [
                    "Looking at all parking locations combined, there are {total_free} free parking spaces available out of {total_spots} total capacity. This gives us an overall availability rate of {percent}% across the entire area.",
                    "When I calculate the numbers from all monitored parking areas, we have {total_free} available spaces out of {total_spots} total spots. The combined availability percentage is {percent}%.",
                    "📊 The total parking availability across all locations shows {total_free} free spaces out of {total_spots} possible parking spots. This means {percent}% of all parking capacity is currently available.",
                    "Combining data from all parking facilities, there are {total_free} open spaces available. With {total_spots} total parking spots monitored, we're seeing {percent}% overall availability.",
                    "The aggregated parking data shows {total_free} free spaces across all {total_spots} monitored parking spots. This results in a {percent}% availability rate for the entire parking network."
                ],
                'outro': [
                    "What else would you like to know about parking?",
                    "Is there anything more about parking availability you'd like to know?",
                    "What would you like to know more about?",
                    "Any other parking information you need?",
                    "What else can I help you with?"
                ]
            },
            {
                'intro': [
                    "I've analyzed the current occupancy data from all monitored locations.",
                    "The monitoring systems are providing real-time occupancy information.",
                    "Here's your parking report based on the latest sensor data from parking management systems."
                ],
                'location': [
                    "🅿️ The parking management system at {location} reports {free} available spaces out of {total} total capacity. This represents {percent}% availability, which means the majority of spaces are currently occupied.",
                    "{location} currently has {free} parking spaces available. The facility's total capacity is {total} spots, so we're looking at {percent}% availability at this specific location.",
                    "🚗 Parking data from {location} shows {free} empty spaces available right now. With a total capacity of {total} vehicles, this location is operating at {percent}% availability."
                ],
                'summary': [
                    "📈 The combined parking statistics show {total_free} available spaces across all monitored locations. With {total_spots} total parking capacity, this represents {percent}% overall availability.",
                    "When I analyze all the parking data together, we have {total_free} free spaces out of {total_spots} total capacity. This gives us a network-wide availability rate of {percent}%."
                ],
                'outro': [
                    "What else would you like to know?",
                    "Is there anything more about parking you'd like to know?",
                    "What would you like to know more about?"
                ]
            },
            {
                'intro': [
                    "I've processed the latest parking occupancy data..",
                    "Your parking report is ready..",
                    "Let me decode the occupancy patterns for you."
                ],
                'location': [
                    "The parking monitoring sensors at {location} are detecting {free} unoccupied spaces out of a total facility capacity of {total} parking spots. This translates to {percent}% availability at this specific location.",
                    "Current occupancy data from {location} indicates {free} available parking spaces. The facility is designed to accommodate {total} vehicles, which means {percent}% of the parking capacity is currently unused.",
                    "Parking space sensors at {location} report {free} free spots available right now. With the facility's maximum capacity being {total} spaces, we're seeing {percent}% availability."
                ],
                'summary': [
                    "Statistical analysis of parking occupancy across all monitored facilities reveals {total_free} available spaces out of {total_spots} total capacity. This produces an overall availability metric of {percent}% for the entire parking network.",
                    "The aggregated parking occupancy data shows {total_free} free spaces distributed across {total_spots} total monitored parking spots. This results in a network-wide availability percentage of {percent}%."
                ],
                'outro': [
                    "What else would you like to know?",
                    "Is there anything more you need to know?",
                    "What would you like to know more about?"
                ]
            }
        ]
        
        #Location-specific templates for single location queries
        self.location_specific_templates = {
            'intro': [
                "Here's the current parking situation at {location}:",
                "Let me check the parking availability at {location}:",
                "Current parking status for {location}:",
                "Here's what I found for parking at {location}:"
            ],
            'single_location': [
                "🅿️ At {location}, there are {free} parking spaces available out of {total} total spots. That's {percent}% availability.",
                "🚗 {location} currently has {free} free spaces with a total capacity of {total} spots ({percent}% available).",
                "📍 The parking facility at {location} shows {free} available spaces out of {total} total ({percent}% availability).",
                "🚙 {location} reports {free} open parking spaces from a total of {total} spots - {percent}% availability right now."
            ],
            'not_found': [
                "I couldn't find parking data for {location}. Let me show you all available parking locations instead:",
                "No specific data found for {location}. Here's the current parking situation at all monitored locations:"
            ]
        }
        
        #Weather-specific location templates for single location queries
        self.weather_location_specific_templates = {
            'intro': [
                "Here's the current weather at {location}:",
                "Let me check the weather conditions at {location}:",
                "Current weather status for {location}:",
                "Here's what I found for weather at {location}:"
            ],
            'single_location': [
                "🌡️ At {location}, the temperature is {temp}°C with {humidity}% humidity.",
                "📍 {location} is currently {temp}°C with humidity at {humidity}%.",
                "🌤️ Weather conditions at {location}: {temp}°C temperature and {humidity}% humidity.",
                "☁️ {location} reports {temp}°C and {humidity}% humidity right now."
            ],
            'not_found': [
                "I couldn't find weather data for {location}. Let me show you all available weather locations instead:",
                "No specific data found for {location}. Here's the current weather situation at all monitored locations:"
            ]
        }
        
        #Traffic-specific location templates for single location queries
        self.traffic_location_specific_templates = {
            'intro': [
                "Here's the current traffic situation at {location}:",
                "Let me check the traffic conditions at {location}:",
                "Current traffic status for {location}:",
                "Here's what I found for traffic at {location}:"
            ],
            'single_location': [
                "🚦 At {location}, there are {vehicles_in} vehicles entering and {vehicles_out} vehicles exiting with an average speed of {speed} km/h. I also see {pedestrians} pedestrians and {cyclists} cyclists in the area.",
                "🚗 {location} currently has {vehicles_in} incoming and {vehicles_out} outgoing vehicles, moving at {speed} km/h average speed. The junction serves {pedestrians} pedestrians and {cyclists} cyclists.",
                "📍 Traffic flow at {location}: {vehicles_in} vehicles in, {vehicles_out} vehicles out, average speed {speed} km/h, plus {pedestrians} pedestrians and {cyclists} cyclists.",
                "🛣️ {location} reports {vehicles_in} entering vehicles, {vehicles_out} exiting vehicles at {speed} km/h, with {pedestrians} pedestrians and {cyclists} cyclists using the junction."
            ],
            'speed_focused': [
                "🚦 Traffic speed at {location} is {speed} km/h.",
                "🏃 Vehicles are moving at {speed} km/h at {location}.",
                "📊 The average speed at {location} is {speed} km/h."
            ],
            'pedestrians_focused': [
                "🚶 There are {pedestrians} pedestrians at {location}.",
                "👥 {location} has {pedestrians} pedestrians in the area.",
                "🚶‍♂️ Pedestrian count at {location}: {pedestrians} people."
            ],
            'cyclists_focused': [
                "🚴 There are {cyclists} cyclists at {location}.",
                "🚲 {location} has {cyclists} cyclists using the junction.",
                "🚴‍♂️ Cyclist count at {location}: {cyclists} people."
            ],
            'vehicles_focused': [
                "🚗 Vehicle flow at {location}: {vehicles_in} entering, {vehicles_out} exiting.",
                "🚙 {location} has {vehicles_in} incoming and {vehicles_out} outgoing vehicles.",
                "📈 Traffic flow at {location}: {vehicles_in} in, {vehicles_out} out."
            ]
        }
        
        #Templates for traffic 
        self.traffic_templates = [
            {
                'intro': [
                    " Here's what the current traffic conditions look like.",
                    " Let me give you an update on the traffic situation right now. ",
                    " Here's your traffic flow update based on data from junction monitoring systems.",
                    "Let me break down what's happening on the roads right now.",
                    "Here's what the transportation monitoring systems are reporting."
                ],
                'location': [
                    "At {location}, traffic sensors are detecting {vehicles_in} vehicles entering the junction and {vehicles_out} vehicles exiting. The average speed through this area is {speed} km/h. Additionally, pedestrian counters show {pedestrians} people walking through the area, while cyclist detection systems record {cyclists} cyclists passing through the junction.",
                    "The traffic monitoring station at {location} reports {vehicles_in} incoming vehicles and {vehicles_out} outgoing vehicles. Vehicle speeds are averaging {speed} km/h through this junction. The area also accommodates {pedestrians} pedestrians on foot and {cyclists} cyclists, showing this is a multi-modal transportation point.",
                    "📍 Current data from {location} shows {vehicles_in} vehicles flowing into the junction while {vehicles_out} vehicles are leaving. Traffic is moving at an average speed of {speed} km/h. Pedestrian sensors indicate {pedestrians} people walking in the area, and bicycle counters show {cyclists} cyclists using the junction.",
                    "Traffic flow at {location} indicates {vehicles_in} vehicles entering and {vehicles_out} vehicles departing the area. The speed sensors show an average of {speed} km/h for vehicle movement. Pedestrian detection systems record {pedestrians} people walking, while cycling infrastructure shows {cyclists} cyclists actively using this junction.",
                    "The junction at {location} is processing {vehicles_in} incoming vehicles against {vehicles_out} outgoing vehicles. Speed measurements show traffic moving at {speed} km/h on average. The monitoring systems also detect {pedestrians} pedestrians moving through the area and {cyclists} cyclists utilizing the junction infrastructure."
                ],
                'summary': [
                    "Looking at traffic data from all monitoring locations, the average vehicle speed across the entire network is {avg_speed} km/h.",
                    "When I calculate the speeds from all traffic monitoring points, the network-wide average comes out to {avg_speed} km/h.",
                    "The mathematical average of vehicle speeds across all monitored locations shows {avg_speed} km/h.",
                    "Averaging the speed measurements from all traffic sensors, we get {avg_speed} km/h across the monitored network.",
                    "The mean speed calculation across all traffic monitoring stations shows {avg_speed} km/h."
                ],
                'outro': [
                    "What else would you like to know about traffic?",
                    "Is there anything more about traffic conditions you'd like to know?",
                    "What would you like to know more about?",
                    "Any other traffic information you need?",
                    "What else can I help you with?"
                ]
            },
            {
                'intro': [
                    "I've processed data from junction sensors and vehicle detection systems across the network.",
                    "Here's your detailed traffic analysis based on real-time sensor data from vehicle counting and speed detection systems."
                ],
                'location': [
                    "The traffic management system at {location} reports {vehicles_in} vehicles entering the junction and {vehicles_out} vehicles leaving. Speed detection shows vehicles moving at {speed} km/h. The junction serves multiple transportation modes with {pedestrians} pedestrians walking through and {cyclists} cyclists utilizing the area.",
                    "{location} is currently processing {vehicles_in} incoming vehicles with {vehicles_out} vehicles exiting the junction. The speed monitoring indicates {speed} km/h average vehicle velocity. Pedestrian counting systems show {pedestrians} people on foot, while bicycle detection records {cyclists} cyclists actively using the junction.",
                    "Traffic data from {location} shows {vehicles_in} vehicles flowing in against {vehicles_out} vehicles flowing out. Vehicle speed sensors indicate {speed} km/h average movement. The area also accommodates non-motorized transport with {pedestrians} pedestrians walking and {cyclists} cyclists passing through the junction."
                ],
                'summary': [
                    "The combined traffic analysis shows an average speed of {avg_speed} km/h across all monitored junctions. This speed metric represents the overall traffic flow performance throughout the network.",
                    "When I analyze speed data from all traffic monitoring points, the network average settles at {avg_speed} km/h."
                ],
                'outro': [
                    "What else would you like to know?",
                    "Is there anything more about traffic you'd like to know?",
                    "What would you like to know more about?"
                ]
            },
            {
                'intro': [
                    "I've decoded the latest traffic flow data from junction monitoring systems.",
                    "Your traffic intelligence report is ready.",
                    "Let me break down the current transportation dynamics across all junction points."
                ],
                'location': [
                    "Traffic sensors at {location} are detecting {vehicles_in} vehicles entering the junction while simultaneously recording {vehicles_out} vehicles exiting. Speed measurement systems show vehicles traveling at {speed} km/h. The junction infrastructure also supports {pedestrians} pedestrians moving through the area and {cyclists} cyclists utilizing dedicated cycling paths or shared spaces.",
                    "Current traffic flow at {location} shows {vehicles_in} incoming vehicles balanced against {vehicles_out} outgoing vehicles. Speed detection equipment measures {speed} km/h for vehicle movement. Pedestrian monitoring systems record {pedestrians} people walking through the junction, while cycling counters show {cyclists} cyclists actively using the transportation network.",
                    "Junction monitoring at {location} indicates {vehicles_in} vehicles flowing into the area with {vehicles_out} vehicles departing. The average vehicle speed is measured at {speed} km/h. The multi-modal nature of this junction is evident with {pedestrians} pedestrians on foot and {cyclists} cyclists sharing the transportation space."
                ],
                'summary': [
                    "Statistical analysis of speed measurements from all traffic monitoring locations produces an average of {avg_speed} km/h across the network. This speed metric provides insight into overall traffic flow dynamics and potential congestion patterns.",
                    "The aggregated speed data from all junction monitoring points shows {avg_speed} km/h as the network-wide average.."
                ],
                'outro': [
                    "What else would you like to know?",
                    "Is there anything more you need to know?",
                    "What would you like to know more about?"
                ]
            }
        ]
        
        #emojis for different conditions
        self.weather_emojis = {
            'cold': ['🥶', '❄️', '🧊'],
            'cool': ['😌', '🌬️', '🍃'],
            'warm': ['😊', '🌤️', '☀️'],
            'hot': ['🥵', '🔥', '🌞']
        }
        
        self.parking_emojis = {
            'good': ['✅', '🟢', '👍'],
            'bad': ['❌', '🔴', '😟']
        }
        
        self.traffic_emojis = {
            'fast': ['🏃', '✈️', '🚀'],
            'normal': ['🚗', '🚙', '🛣️'],
            'slow': ['🐌', '🚧', '😴']
        }
    ##Categorize temperature
    def get_weather_condition(self, temp: float) -> str:
        if temp < 10:
            return 'cold'
        elif temp < 20:
            return 'cool'
        elif temp < 30:
            return 'warm'
        else:
            return 'hot'
    #Categorize parking availability
    def get_parking_status(self, free: int, total: int) -> str:
        if total == 0:
            return 'medium'
        if total == 20:
            if free < 3:
                return 'bad'
            else:
                return 'good'
    #Categorize traffic speed
    def get_traffic_status(self, speed: float) -> str:
        if speed >= 50:
            return 'fast'
        elif speed >= 30:
            return 'normal'
        else:
            return 'slow'
    #extract location name
    def format_location_name(self, location_id: str) -> str:
        if ':' in location_id:
            name = location_id.split(':')[-1]
            formatted = re.sub(r'(?<!^)(?=[A-Z])', ' ', name)
            return formatted
        return location_id

    #traffic-specific location response generation method
    def generate_location_specific_traffic_response(self, data: List[Dict[str, Any]], requested_location: str, original_question: str) -> str:
        """Generate response for a specific traffic location request"""
        if not data:
            return f"I couldn't find traffic data for {requested_location} right now. Please try again later!"
        
        try:
            if len(data) == 1:
                item = data[0]
                location_name = self.format_location_name(item.get('location_name', item.get('id', requested_location)))
                if ':' in location_name and 'Junction:' in location_name:#handle traffic ID format
                    location_name = location_name.split(':')[-1]
                    location_name = re.sub(r'(?<!^)(?=[A-Z])', ' ', location_name)
                speed = item.get('avgSpeed', 0)
                vehicles_in = item.get('vehiclesIn', 0)
                vehicles_out = item.get('vehiclesOut', 0)
                pedestrians = item.get('pedestrians', 0)
                cyclists = item.get('cyclists', 0)
                question_lower = original_question.lower()
                print(f"DEBUG: Processing traffic question: '{original_question}'")
                print(f"DEBUG: Location name: {location_name}")
                print(f"DEBUG: Data length: {len(data)}")
                print(f"DEBUG: Requested location: {requested_location}")
                if any(word in question_lower for word in ['pedestrian', 'walking', 'foot', 'people walking']) and not any(word in question_lower for word in ['vehicle', 'car', 'speed', 'cyclist']):
                    print(f"DEBUG: Using pedestrian-focused response")
                    response = f"There are {pedestrians} pedestrians at {location_name}."
                    if 'google_maps_link' in item:
                        response += f" [View Location]({item['google_maps_link']})"
                    return response
                elif any(word in question_lower for word in ['cyclist', 'cycling', 'bike', 'bicycle']) and not any(word in question_lower for word in ['vehicle', 'car', 'speed', 'pedestrian']):
                    print(f"DEBUG: Using cyclist-focused response")
                    response = f"There are {cyclists} cyclists at {location_name}."
                    if 'google_maps_link' in item:
                        response += f" [View Location]({item['google_maps_link']})"
                    return response
                elif any(word in question_lower for word in ['speed', 'fast', 'slow', 'km/h', 'mph']) and not any(word in question_lower for word in ['vehicle', 'car', 'pedestrian', 'cyclist']):
                    print(f"DEBUG: Using speed-focused response")
                    response = f"Traffic speed at {location_name} is {speed} km/h."
                    if 'google_maps_link' in item:
                        response += f" [View Location]({item['google_maps_link']})"
                    return response
                elif any(word in question_lower for word in ['vehicle', 'car', 'flow', 'enter', 'exit', 'incoming', 'outgoing']) and not any(word in question_lower for word in ['speed', 'pedestrian', 'cyclist']):
                    print(f"DEBUG: Using vehicle-focused response")
                    response = f"Vehicle flow at {location_name}: {vehicles_in} entering, {vehicles_out} exiting."
                    if 'google_maps_link' in item:
                        response += f" [View Location]({item['google_maps_link']})"
                    return response
                else:
                    print(f"DEBUG: Using comprehensive traffic response")
                    intro = random.choice(self.traffic_location_specific_templates['intro']).format(location=location_name)
                    status = self.get_traffic_status(speed)
                    emoji = random.choice(self.traffic_emojis[status])
                    response_text = random.choice(self.traffic_location_specific_templates['single_location']).format(
                        location=location_name, speed=speed, vehicles_in=vehicles_in, 
                        vehicles_out=vehicles_out, pedestrians=pedestrians, cyclists=cyclists
                    )
                    if 'google_maps_link' in item:
                        response_text += f" [View Location]({item['google_maps_link']})"
                    
                    return f"{intro} {emoji} {response_text}"
            else:
                return self.generate_traffic_response(data, original_question)
        except Exception as e:
            print(f"Error in generate_location_specific_traffic_response: {e}")
            return f"I found some traffic data for {requested_location} but had trouble formatting the response. Let me try showing all traffic locations instead."

    def generate_location_specific_weather_response(self, data: List[Dict[str, Any]], requested_location: str, original_question: str) -> str:
        """Generate response for a specific weather location request"""
        if not data:
            return f"I couldn't find weather data for {requested_location} right now. Please try again later!"
        
        try:
            if len(data) == 1:
                item = data[0]
                location_name = self.format_location_name(item.get('location_name', item.get('id', requested_location)))
                if ':' in location_name and 'Weather:' in location_name:
                    location_name = location_name.split(':')[-1]
                    location_name = re.sub(r'(?<!^)(?=[A-Z])', ' ', location_name)
                temp = item.get('temperature', 0)
                humidity = item.get('humidity', 0)
                condition = self.get_weather_condition(temp)
                emoji = random.choice(self.weather_emojis[condition])
                intro = random.choice(self.weather_location_specific_templates['intro']).format(location=location_name)
                response_text = random.choice(self.weather_location_specific_templates['single_location']).format(
                    location=location_name,
                    temp=temp,
                    humidity=humidity
                )
                if 'google_maps_link' in item:
                    response_text += f" [View Location]({item['google_maps_link']})"
                
                return f"{intro} {emoji} {response_text}"
            else:
                return self.generate_weather_response(data, original_question)
        except Exception as e:
            print(f"Error in generate_location_specific_weather_response: {e}")
            return f"I found some weather data for {requested_location} but had trouble formatting the response. Let me try showing all weather locations instead."
    def generate_location_specific_parking_response(self, data: List[Dict[str, Any]], requested_location: str, original_question: str) -> str:
        """Generate response for a specific location request"""
        if not data:
            return f"I couldn't find parking data for {requested_location} right now. Please try again later!"
        
        try:
            if len(data) == 1:
                item = data[0]
                location_name = self.format_location_name(item.get('location_name', item.get('id', requested_location)))
                free = item.get('freeSpaces', 0)
                total = item.get('totalSpaces', 0)
                percent = round((free / total * 100), 1) if total > 0 else 0
                intro = random.choice(self.location_specific_templates['intro']).format(location=location_name)
                response_text = random.choice(self.location_specific_templates['single_location']).format(
                    location=location_name,
                    free=free,
                    total=total,
                    percent=percent
                )

                if 'google_maps_link' in item:
                    response_text += f" [View Location]({item['google_maps_link']})"
                
                return f"{intro} {response_text}"
            else:
                return self.generate_parking_response(data, original_question)
        except Exception as e:
            print(f"Error in generate_location_specific_parking_response: {e}")
            return f"I found some data for {requested_location} but had trouble formatting the response. Let me try showing all parking locations instead."
    
    def generate_weather_response(self, data: List[Dict[str, Any]], original_question: str) -> str:
        if not data:
            return "😔 I couldn't find any weather data right now. Please try again later!"
        template = random.choice(self.weather_templates)
        response = random.choice(template['intro']) + " "
        temps = [item.get('temperature', 0) for item in data]
        humidities = [item.get('humidity', 0) for item in data]
        avg_temp = round(sum(temps) / len(temps), 1) if temps else 0
        avg_humidity = round(sum(humidities) / len(humidities), 1) if humidities else 0
        location_responses = []
        for item in data[:3]:
            location_name = self.format_location_name(item.get('location_name', item.get('id', 'Unknown')))
            temp = item.get('temperature', 0)
            humidity = item.get('humidity', 0)
            condition = self.get_weather_condition(temp)
            emoji = random.choice(self.weather_emojis[condition])
            location_text = random.choice(template['location']).format(
                location=location_name,
                temp=temp,
                humidity=humidity
            )
            
            if 'google_maps_link' in item:
                location_text += f" [📍]({item['google_maps_link']})"
            
            location_responses.append(emoji + " " + location_text)
        
        if len(location_responses) > 1:
            connectors = [", ", " and ", ", also ", ", plus "]
            response += location_responses[0]
            for i in range(1, len(location_responses)):
                response += random.choice(connectors) + location_responses[i]
        else:
            response += location_responses[0]
        
        response += ". " + random.choice(template['summary']).format(
            avg_temp=avg_temp,
            avg_humidity=avg_humidity
        )
        
        response += " " + random.choice(template['outro'])
        return response
    
    def generate_parking_response(self, data: List[Dict[str, Any]], original_question: str) -> str:
        if not data:
            return "🚫 No parking data available at the moment. Try again soon!"
        template = random.choice(self.parking_templates)
        response = random.choice(template['intro']) + " "
        total_free = sum(item.get('freeSpaces', 0) for item in data)
        total_spots = sum(item.get('totalSpaces', 0) for item in data)
        overall_percent = round((total_free / total_spots * 100), 1) if total_spots > 0 else 0
        location_responses = []
        for item in data[:3]:
            location_name = self.format_location_name(item.get('location_name', item.get('id', 'Unknown')))
            free = item.get('freeSpaces', 0)
            total = item.get('totalSpaces', 0)
            percent = round((free / total * 100), 1) if total > 0 else 0
            status = self.get_parking_status(free, total)
            emoji = random.choice(self.parking_emojis[status])
            
            location_text = random.choice(template['location']).format(
                location=location_name,
                free=free,
                total=total,
                percent=percent
            )
            if 'google_maps_link' in item:
                location_text += f" [🗺️]({item['google_maps_link']})"
            
            location_responses.append(emoji + " " + location_text)
        response += "; ".join(location_responses)
        response += ". " + random.choice(template['summary']).format(
            total_free=total_free,
            total_spots=total_spots,
            percent=overall_percent
        )
        response += " " + random.choice(template['outro'])
        return response
    
    def generate_traffic_response(self, data: List[Dict[str, Any]], original_question: str) -> str:
        """Generate traffic response from data"""
        if not data:
            return "🚦 No traffic data available right now. Check back later!"
        template = random.choice(self.traffic_templates)
        response = random.choice(template['intro']) + " "
        speeds = [item.get('avgSpeed', 0) for item in data]
        avg_speed = round(sum(speeds) / len(speeds), 1) if speeds else 0
        location_responses = []
        for item in data[:3]:
            location_name = self.format_location_name(item.get('location_name', item.get('id', 'Unknown')))
            speed = item.get('avgSpeed', 0)
            vehicles_in = item.get('vehiclesIn', 0)
            vehicles_out = item.get('vehiclesOut', 0)
            vehicles_total = vehicles_in + vehicles_out
            pedestrians = item.get('pedestrians', 0)
            cyclists = item.get('cyclists', 0)
            status = self.get_traffic_status(speed)
            emoji = random.choice(self.traffic_emojis[status])
            
            location_text = random.choice(template['location']).format(
                location=location_name,
                speed=speed,
                vehicles_in=vehicles_in,
                vehicles_out=vehicles_out,
                vehicles_total=vehicles_total,
                pedestrians=pedestrians,
                cyclists=cyclists
            )
            if 'google_maps_link' in item:
                location_text += f" [🗺️]({item['google_maps_link']})"
            
            location_responses.append(emoji + " " + location_text)
        
        separators = ["; ", " | ", " — ", ", while "]
        response += location_responses[0]
        for i in range(1, len(location_responses)):
            response += random.choice(separators) + location_responses[i]
        response += ". " + random.choice(template['summary']).format(avg_speed=avg_speed)
        response += " " + random.choice(template['outro'])
        return response
    
    ###generate appropriate response based on entity type with location awareness
    def generate_response(self, entity_type: str, data: List[Dict[str, Any]], original_question: str, requested_location: Optional[str] = None) -> str:
        try:
            print(f"DEBUG: generate_response called with entity_type={entity_type}, data_length={len(data) if data else 0}, requested_location={requested_location}")
            
            if entity_type == 'WeatherObserved':
                if requested_location and len(data) == 1:
                    return self.generate_location_specific_weather_response(data, requested_location, original_question)
                else:
                    return self.generate_weather_response(data, original_question)
            elif entity_type == 'ParkingSpot':
                if requested_location and len(data) == 1:
                    return self.generate_location_specific_parking_response(data, requested_location, original_question)
                else:
                    return self.generate_parking_response(data, original_question)
            elif entity_type == 'Traffic':
                print(f"DEBUG: Traffic entity detected. requested_location={requested_location}, data_length={len(data)}")
                if requested_location and len(data) == 1:
                    print(f"DEBUG: Using location-specific traffic response")
                    return self.generate_location_specific_traffic_response(data, requested_location, original_question)
                else:
                    print(f"DEBUG: Using general traffic response")
                    return self.generate_traffic_response(data, original_question)
            else:
                return "I found some data but I'm not sure how to interpret it. Can you try asking differently?"
        except Exception as e:
            print(f"Error in generate_response: {e}")
            return f"I found the data you requested, but encountered an error while formatting the response. Please try asking again."


class SimpleFIWARETester:
    """Enhanced version with location-aware response generation"""
    
    def __init__(self, fiware_url="https://imiq-public.et.uni-magdeburg.de/api/orion", api_key="A9ioeCoyn7Imksmy"):
        self.fiware_url = fiware_url
        self.api_key = api_key
        self.translator = SimpleFIWARERuleBasedTranslator()
        self.response_generator = RuleBasedResponseGenerator()

    def normalize_fiware_data(self, raw_data):
        """Normalize FIWARE NGSI format to simple flat structure"""
        if not isinstance(raw_data, list):
            return raw_data
        
        normalized = []
        
        for entity in raw_data:
            flat_entity = {
                "id": entity.get("id", ""),
                "type": entity.get("type", "")
            }
            
            entity_id = entity.get("id", "")
            if ":" in entity_id:
                location_name = entity_id.split(":")[-1]
                flat_entity["location_name"] = location_name
            
            for key, value in entity.items():
                if key not in ["id", "type"] and isinstance(value, dict):
                    if "value" in value:
                        # Extract the actual value from FIWARE format
                        actual_value = value["value"]
                        flat_entity[key] = actual_value
                        
                        # Special handling for geo:point
                        if key == "location" and isinstance(actual_value, str):
                            coords = actual_value.replace(" ", "").split(",")
                            if len(coords) == 2:
                                flat_entity["latitude"] = float(coords[0])
                                flat_entity["longitude"] = float(coords[1])
                                flat_entity["google_maps_link"] = f"https://maps.google.com/?q={coords[0]},{coords[1]}"
            
            normalized.append(flat_entity)
        
        return normalized

    def execute_fiware_query(self, query_path):
        """Execute FIWARE-QL query and return normalized JSON response"""
        try:
            headers = {'x-api-key': self.api_key}
            full_url = f"{self.fiware_url}{query_path}"
            
            response = requests.get(full_url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                raw_data = response.json()
                normalized_data = self.normalize_fiware_data(raw_data)
                return {
                    "success": True,
                    "data": normalized_data,
                    "count": len(normalized_data) if isinstance(normalized_data, list) else 1
                }
            else:
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}",
                    "message": response.text
                }
        except Exception as e:
            return {
                "success": False,
                "error": "Exception",
                "message": str(e)
            }

    def process_natural_query(self, natural_query):
        """Enhanced pipeline with location awareness and fallback mechanism"""
        print(f"Processing: {natural_query}")
        
        try:
            requested_location = self.translator.extract_location_from_query(natural_query)
        
            translation_result = self.translator.translate(natural_query)
            if isinstance(translation_result, tuple):
                fiware_query, fallback_query = translation_result
            else:
                fiware_query = translation_result
                fallback_query = None
            
            print(f"Generated: {fiware_query}")
            if fallback_query:
                print(f"Fallback query: {fallback_query}")
            print(f"Requested location: {requested_location}")
        
            result = self.execute_fiware_query(fiware_query)
            print(f"FIWARE API Response Success: {result['success']}")
            
            if not result["success"] and fallback_query:
                print(f"Specific query failed, trying fallback: {fallback_query}")
                result = self.execute_fiware_query(fallback_query)
                print(f"Fallback query success: {result['success']}")
                if result["success"] and requested_location and result.get('data'):
                    all_data = result['data']
                    filtered_data = []
                    for item in all_data:
                        item_id = item.get('id', '').lower()
                        location_name = item.get('location_name', '').lower()
                        requested_lower = requested_location.lower()
                        
                        if (requested_lower in item_id or 
                            requested_lower in location_name or
                            item_id.endswith(requested_lower)):
                            filtered_data.append(item)
                    
                    if filtered_data:
                        result['data'] = filtered_data
                        print(f"Filtered data to {len(filtered_data)} items for location: {requested_location}")
                    else:
                        print(f"No data found for location: {requested_location}")
                        result['data'] = all_data
            if result["success"]:
                print(f"Data received: {len(result['data']) if isinstance(result['data'], list) else 'N/A'} items")
                entity_type = result['data'][0].get('type', 'Unknown') if result['data'] else 'Unknown'
                explanation = self.response_generator.generate_response(
                    entity_type, 
                    result['data'], 
                    natural_query,
                    requested_location  
                )
                return {
                    "success": True,
                    "message": explanation,
                    "data": result["data"],
                    "debug_info": {
                        "fiware_query": fiware_query,
                        "fallback_used": fallback_query is not None,
                        "data_count": len(result['data']) if isinstance(result['data'], list) else 0,
                        "entity_type": entity_type,
                        "requested_location": requested_location
                    }
                }
            else:
                error_emojis = ['😔', '😕', '🤷', '😅', '🙈']
                error_messages = [
                    f"{random.choice(error_emojis)} I couldn't fetch the data right now. Please try again in a moment!",
                    f"{random.choice(error_emojis)} Oops! Something went wrong. Let me try again in a bit!",
                    f"{random.choice(error_emojis)} The data seems to be unavailable at the moment. Try again soon!",
                    f"{random.choice(error_emojis)} Having trouble connecting right now. Give it another shot!"
                ]
                
                return {
                    "success": False,
                    "message": random.choice(error_messages),
                    "debug_info": {
                        "fiware_query": fiware_query,
                        "fallback_query": fallback_query,
                        "error": result.get('error', 'Unknown error'),
                        "error_message": result.get('message', 'No error message'),
                        "requested_location": requested_location
                    }
                }
        except Exception as e:
            print(f"Error in process_natural_query: {e}")
            print(f"Query was: {natural_query}")
            return {
                "success": False,
                "message": f"🤖 Sorry, I encountered an error while processing your request: {str(e)}",
                "debug_info": {
                    "error": "Processing Exception",
                    "error_message": str(e),
                    "query": natural_query
                }
            }

#setup falsk
app = Flask(__name__)

#start chatbot
chatbot = SimpleFIWARETester()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.get_json()
        user_message = data.get('message', '').strip()
        
        if not user_message:
            return jsonify({
                'success': False,
                'message': 'Please enter a message. 💬'
            })
        
        result = chatbot.process_natural_query(user_message)
        
        response_data = {
            'success': result['success'],
            'message': result['message'],
            'timestamp': datetime.now().strftime('%H:%M')
        }
        
        if 'debug_info' in result:
            response_data['debug'] = result['debug_info']
        
        return jsonify(response_data)
        
    except Exception as e:
        print(f"Error processing chat: {e}")
        error_emojis = ['🤖', '⚡', '🔧', '🛠️']
        return jsonify({
            'success': False,
            'message': f'{random.choice(error_emojis)} Sorry, I encountered an error while processing your request. Please try again!',
            'timestamp': datetime.now().strftime('%H:%M'),
            'debug': {'error': str(e)}
        })

if __name__ == '__main__':
    print("Starting Flask server")
    app.run(debug=False, host='0.0.0.0', port=5000)