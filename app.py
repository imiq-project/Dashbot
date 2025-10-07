import re
from typing import Optional, List, Dict, Any
import json
from flask import Flask, render_template, request, jsonify
import requests
from datetime import datetime
import random
import os

class LanguageDetector:
    """simple language detector for English and German - ignores location names"""
    
    def __init__(self):
        self.english_words = {
            'the', 'is', 'are', 'weather', 'parking', 'traffic', 'where',
            'what', 'how', 'many', 'current', 'show', 'me', 'available',
            'free', 'spaces', 'temperature', 'humidity', 'speed', 'at', 'in',
            'there', 'any', 'check', 'tell', 'find', 'get'
        }
        
        self.german_words = {
            'das', 'der', 'die', 'ist', 'sind', 'wetter', 'parken', 'verkehr',
            'wo', 'was', 'wie', 'viele', 'aktuell', 'zeige', 'mir', 'verfügbar',
            'frei', 'plätze', 'temperatur', 'feuchtigkeit', 'geschwindigkeit',
            'gibt', 'es', 'einen', 'eine', 'im', 'in', 'am', 'beim', 'zur',
            'zum', 'den', 'dem', 'des'
        }
        
        # Location names to ignore (both English and German)
        self.location_names = {
            'scienceharbor', 'science', 'harbor', 'hafen', 'wissenschaftshafen',
            'sciencehub', 'hub', 'wissenschaftszentrum', 'zentrum',
            'facultycs', 'faculty', 'cs', 'fakultät', 'informatik',
            'northpark', 'north', 'park', 'nordpark', 'nord',
            'unimensa', 'uni', 'mensa', 'cafeteria', 'kantine',
            'library', 'lib', 'bibliothek', 'bib',
            'welcomecenter', 'welcome', 'center', 'willkommenszentrum',
            'geschwisterpark', 'geschwister'
        }
    
    def detect(self, text: str) -> str:
        """Detect if text is in English or German - ignores location names"""
        # Convert to lowercase and split into words
        words = text.lower().split()
        
        # Filter out location names
        filtered_words = [
            word for word in words 
            if word not in self.location_names
        ]
        
        # Convert to set for matching
        word_set = set(filtered_words)
        
        # Count matches for each language
        english_score = len(word_set & self.english_words)
        german_score = len(word_set & self.german_words)
        
        print(f"DEBUG Language Detection:")
        print(f"  Original text: {text}")
        print(f"  Filtered words: {filtered_words}")
        print(f"  English score: {english_score}")
        print(f"  German score: {german_score}")
        
        if german_score > english_score:
            print(f"  -> Detected: German")
            return 'de'
        elif english_score > german_score:
            print(f"  -> Detected: English")
            return 'en'
        else:
            # If no clear match, check for umlauts (strong indicator of German)
            if any(char in text for char in 'äöüßÄÖÜ'):
                print(f"  -> Detected: German (umlauts)")
                return 'de'
            
            # Check for common German sentence patterns
            german_patterns = ['gibt es', 'wie ist', 'wo ist', 'was ist', 'im ', 'am ', 'beim ']
            if any(pattern in text.lower() for pattern in german_patterns):
                print(f"  -> Detected: German (patterns)")
                return 'de'
            
            print(f"  -> Detected: English (default)")
            return 'en'  # Default to English
##Rule-based system for translating natural language to FIWARE-QL queries with location awareness
class SimpleFIWARERuleBasedTranslator:
    def __init__(self):
        # ENGLISH KEYWORDS 
        self.entity_keywords_en = {
            # Traffic-related keywords 
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
        
        # GERMAN KEYWORDS 
        self.entity_keywords_de = {
            # Traffic-related keywords
            'verkehr': 'Traffic',
            'straße': 'Traffic',
            'strasse': 'Traffic',
            'straßen': 'Traffic',
            'strassen': 'Traffic',
            'weg': 'Traffic',
            'wege': 'Traffic',
            'fahrzeug': 'Traffic',
            'fahrzeuge': 'Traffic',
            'auto': 'Traffic',
            'autos': 'Traffic',
            'wagen': 'Traffic',
            'kraftfahrzeug': 'Traffic',
            'kfz': 'Traffic',
            'pkw': 'Traffic',
            'radfahrer': 'Traffic',
            'radfahrerin': 'Traffic',
            'radler': 'Traffic',
            'fahrrad': 'Traffic',
            'fahrräder': 'Traffic',
            'rad': 'Traffic',
            'räder': 'Traffic',
            'radfahren': 'Traffic',
            'velo': 'Traffic',
            'fußgänger': 'Traffic',
            'fussgänger': 'Traffic',
            'fußgaenger': 'Traffic',
            'fussgaenger': 'Traffic',
            'fußgängerin': 'Traffic',
            'passant': 'Traffic',
            'passanten': 'Traffic',
            'gehen': 'Traffic',
            'laufen': 'Traffic',
            'spazieren': 'Traffic',
            'gehweg': 'Traffic',
            'bürgersteig': 'Traffic',
            'fußweg': 'Traffic',
            'zebrastreifen': 'Traffic',
            'übergang': 'Traffic',
            'überquerung': 'Traffic',
            'geschwindigkeit': 'Traffic',
            'tempo': 'Traffic',
            'kmh': 'Traffic',
            'stundenkilometer': 'Traffic',
            'schnell': 'Traffic',
            'langsam': 'Traffic',
            'kreuzung': 'Traffic',
            'kreuzungen': 'Traffic',
            'knotenpunkt': 'Traffic',
            'einmündung': 'Traffic',
            'kreisverkehr': 'Traffic',
            'kreisel': 'Traffic',
            'transport': 'Traffic',
            'mobilität': 'Traffic',
            'pendeln': 'Traffic',
            'pendelverkehr': 'Traffic',
            'verkehrsfluss': 'Traffic',
            'fluss': 'Traffic',
            'stau': 'Traffic',
            'verkehrsstau': 'Traffic',
            'stockung': 'Traffic',
            'behinderung': 'Traffic',
            'engpass': 'Traffic',
            'stoßzeit': 'Traffic',
            'hauptverkehrszeit': 'Traffic',
            'rushhour': 'Traffic',
            'bewegung': 'Traffic',
            'zirkulation': 'Traffic',
            'route': 'Traffic',
            'strecke': 'Traffic',
            'autofahrer': 'Traffic',
            'fahrer': 'Traffic',
            'fahren': 'Traffic',
            
            # Weather-related keywords (Wetter)
            'wetter': 'WeatherObserved',
            'temperatur': 'WeatherObserved',
            'temp': 'WeatherObserved',
            'celsius': 'WeatherObserved',
            'grad': 'WeatherObserved',
            'gradwert': 'WeatherObserved',
            'heiß': 'WeatherObserved',
            'heiss': 'WeatherObserved',
            'warm': 'WeatherObserved',
            'kalt': 'WeatherObserved',
            'kühl': 'WeatherObserved',
            'frisch': 'WeatherObserved',
            'eisig': 'WeatherObserved',
            'gefroren': 'WeatherObserved',
            'kochend': 'WeatherObserved',
            'glühend': 'WeatherObserved',
            'brennend': 'WeatherObserved',
            'schwül': 'WeatherObserved',
            'mild': 'WeatherObserved',
            'gemäßigt': 'WeatherObserved',
            'mäßig': 'WeatherObserved',
            'angenehm': 'WeatherObserved',
            'behaglich': 'WeatherObserved',
            'komfortabel': 'WeatherObserved',
            'feuchtigkeit': 'WeatherObserved',
            'luftfeuchtigkeit': 'WeatherObserved',
            'feucht': 'WeatherObserved',
            'nässe': 'WeatherObserved',
            'nass': 'WeatherObserved',
            'trocken': 'WeatherObserved',
            'dürr': 'WeatherObserved',
            'trockenheit': 'WeatherObserved',
            'drückend': 'WeatherObserved',
            'stickig': 'WeatherObserved',
            'klamm': 'WeatherObserved',
            'druck': 'WeatherObserved',
            'luftdruck': 'WeatherObserved',
            'barometrisch': 'WeatherObserved',
            'atmosphärisch': 'WeatherObserved',
            'klima': 'WeatherObserved',
            'witterung': 'WeatherObserved',
            'bedingungen': 'WeatherObserved',
            'verhältnisse': 'WeatherObserved',
            'vorhersage': 'WeatherObserved',
            'wettervorhersage': 'WeatherObserved',
            'prognose': 'WeatherObserved',
            'meteorologie': 'WeatherObserved',
            'draußen': 'WeatherObserved',
            'außen': 'WeatherObserved',
            'im freien': 'WeatherObserved',
            'luftqualität': 'WeatherObserved',
            'atmosphäre': 'WeatherObserved',
            'umwelt': 'WeatherObserved',
            'jahreszeitlich': 'WeatherObserved',
            'saisonal': 'WeatherObserved',
            'thermisch': 'WeatherObserved',
            
            # Parking-related keywords (Parken)
            'parken': 'ParkingSpot',
            'parkplatz': 'ParkingSpot',
            'parkplätze': 'ParkingSpot',
            'stellplatz': 'ParkingSpot',
            'stellplätze': 'ParkingSpot',
            'abstellplatz': 'ParkingSpot',
            'platz': 'ParkingSpot',
            'plätze': 'ParkingSpot',
            'lücke': 'ParkingSpot',
            'parklücke': 'ParkingSpot',
            'parkfläche': 'ParkingSpot',
            'parkhaus': 'ParkingSpot',
            'parkhäuser': 'ParkingSpot',
            'garage': 'ParkingSpot',
            'garagen': 'ParkingSpot',
            'tiefgarage': 'ParkingSpot',
            'autopark': 'ParkingSpot',
            'parkraum': 'ParkingSpot',
            'bucht': 'ParkingSpot',
            'parkbucht': 'ParkingSpot',
            'stand': 'ParkingSpot',
            'box': 'ParkingSpot',
            'parkbox': 'ParkingSpot',
            'freie plätze': 'ParkingSpot',
            'verfügbar': 'ParkingSpot',
            'verfügbarkeit': 'ParkingSpot',
            'kapazität': 'ParkingSpot',
            'auslastung': 'ParkingSpot',
            'belegung': 'ParkingSpot',
            'belegt': 'ParkingSpot',
            'frei': 'ParkingSpot',
            'reserviert': 'ParkingSpot',
            'behindert': 'ParkingSpot',
            'behindertenparkplatz': 'ParkingSpot',
            'besucher': 'ParkingSpot',
            'besucherparkplatz': 'ParkingSpot',
            'gast': 'ParkingSpot',
            'gäste': 'ParkingSpot',
            'genehmigung': 'ParkingSpot',
            'berechtigung': 'ParkingSpot',
            'zone': 'ParkingSpot',
            'parkzone': 'ParkingSpot',
            'parkuhr': 'ParkingSpot',
            'parkautomat': 'ParkingSpot',
            'valet': 'ParkingSpot',
            'unterirdisch': 'ParkingSpot',
            'untergrund': 'ParkingSpot',
            'überdacht': 'ParkingSpot',
            'gedeckt': 'ParkingSpot',
            'offen': 'ParkingSpot',
            'im freien': 'ParkingSpot',
            'oberfläche': 'ParkingSpot',
            'oberflächenparkplatz': 'ParkingSpot',
            'mehrstöckig': 'ParkingSpot',
            'parkdeck': 'ParkingSpot',
            'struktur': 'ParkingSpot'
        }
        
        # ENGLISH LOCATIONS 
        self.location_mappings_en = {
            #Parking-specific locations
            'scienceharbor': 'ScienceHarbor',
            'science harbor': 'ScienceHarbor',
            'harbor': 'ScienceHarbor',
            
            #Weather-specific locations  
            'sciencehub': 'ScienceHub',
            'science hub': 'ScienceHub',
            'hub': 'ScienceHub',
            
            #Shared locations 
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
        
        self.location_mappings_de = {
            # Parking-specific locations
            'wissenschaftshafen': 'ScienceHarbor',
            'wissenschafts hafen': 'ScienceHarbor',
            'hafen': 'ScienceHarbor',
            
            # Weather-specific locations
            'wissenschaftszentrum': 'ScienceHub',
            'wissenschafts zentrum': 'ScienceHub',
            'zentrum': 'ScienceHub',
            
            # Shared locations
            'fakultät informatik': 'FacultyCS',
            'fakultät': 'FacultyCS',
            'informatik': 'FacultyCS',
            'fakultaet': 'FacultyCS',
            'fakultaet informatik': 'FacultyCS',
            'nordpark': 'NorthPark',
            'nord park': 'NorthPark',
            'nord': 'NorthPark',
            'norden': 'NorthPark',
            'unimensa': 'UniMensa',
            'uni mensa': 'UniMensa',
            'mensa': 'UniMensa',
            'cafeteria': 'UniMensa',
            'kantine': 'UniMensa',
            'speisesaal': 'UniMensa',
            'bibliothek': 'Library',
            'bib': 'Library',
            'bücherei': 'Library',
            'willkommenszentrum': 'WelcomeCenter',
            'willkommens zentrum': 'WelcomeCenter',
            'willkommen': 'WelcomeCenter',
            'empfangszentrum': 'WelcomeCenter',
            'geschwisterpark': 'GeschwisterPark',
            'geschwister park': 'GeschwisterPark',
            'geschwister': 'GeschwisterPark'
        }
        
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
            },
            'wissenschaft': {
                'parking': 'ScienceHarbor',
                'weather': 'ScienceHub',
                'traffic': 'ScienceHub'
            }
        }

    def extract_location_from_query(self, query: str, language: str = 'en') -> Optional[str]:
        query_lower = query.lower().strip()
        all_location_mappings = {**self.location_mappings_en, **self.location_mappings_de}
        entity_type = self.detect_entity_type(query, language)
        entity_context = None
        if entity_type == 'ParkingSpot':
            entity_context = 'parking'
        elif entity_type == 'WeatherObserved':
            entity_context = 'weather'
        elif entity_type == 'Traffic':
            entity_context = 'traffic'
        sorted_locations = sorted(all_location_mappings.items(), key=lambda x: len(x[0]), reverse=True)
        
        for keyword, location in sorted_locations:
            if keyword in query_lower:
                if keyword in ['north', 'nord'] and any(x in query_lower for x in ['northpark', 'north park', 'nordpark', 'nord park']):
                    continue  
                print(f"DEBUG: Found location keyword '{keyword}' -> '{location}' in query: '{query}'")
                return location
        if entity_context:
            for ambiguous_term, context_map in self.context_mappings.items():
                if ambiguous_term in query_lower and entity_context in context_map:
                    resolved_location = context_map[entity_context]
                    print(f"DEBUG: Context-resolved '{ambiguous_term}' -> '{resolved_location}' for {entity_context} in query: '{query}'")
                    return resolved_location
        
        print(f"DEBUG: No location found in query: '{query}'")
        return None

    def detect_entity_type(self, query: str, language: str = 'en') -> str:
        """Entity type detection based on keyword matching with language support"""
        query_lower = query.lower()
        
        entity_keywords = self.entity_keywords_de if language == 'de' else self.entity_keywords_en
        entity_scores = {'Traffic': 0, 'WeatherObserved': 0, 'ParkingSpot': 0}
        for keyword, entity_type in entity_keywords.items():
            if keyword in query_lower:
                entity_scores[entity_type] += 1
        best_entity = max(entity_scores.items(), key=lambda x: x[1])
        if best_entity[1] == 0:
            return None
        
        return best_entity[0]
        
    def translate(self, natural_query: str, language: str = 'en') -> str:
        """Returns entity query with idPattern for location-specific queries"""
        query = natural_query.strip()
        if not query:
            return '/entities'
        
        # Detect entity type
        entity_type = self.detect_entity_type(query, language)
        if not entity_type:
            return '/entities'
        
        # Check for specific location
        specific_location = self.extract_location_from_query(query, language)
        
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
        self.weather_templates_en = [
            {
                'intro': [
                    "Here's what it's like outside right now.",
                    "Let me check the weather for you.",
                    "Here's today's weather.",
                    "Checking the weather now...",
                    "Got the weather info!"
                ],
                'location': [
                    "At {location}, it's {temp}°C with {humidity}% humidity.",
                    "{location} is showing {temp}°C and {humidity}% humidity.",
                    "In {location}: {temp}°C, humidity at {humidity}%.",
                    "{location} has {temp}°C right now, {humidity}% humidity.",
                    "It's {temp}°C in {location} with {humidity}% humidity."
                ],
                'summary': [
                    "The average temperature across all areas is {avg_temp}°C.",
                    "Overall, it's about {avg_temp}°C in the region.",
                    "Averaging it all out: {avg_temp}°C.",
                    "The general temperature is around {avg_temp}°C.",
                    "Across all locations, we're seeing {avg_temp}°C on average."
                ],
                'outro': [
                    "Need anything else?",
                    "What else can I help with?",
                    "Anything more you'd like to know?",
                    "What else?",
                    "Need more info?"
                ]
            },
            {
                'intro': [
                    "Alright, here's the current weather.",
                    "Weather update coming up!",
                    "Let me tell you about the weather.",
                    "Here's how it looks outside.",
                    "Weather check done!"
                ],
                'location': [
                    "{location}: {temp}°C, {humidity}% humidity.",
                    "Right now in {location} it's {temp}°C, humidity is {humidity}%.",
                    "{temp}°C at {location}, humidity level: {humidity}%.",
                    "{location} is at {temp}°C with {humidity}% moisture in the air.",
                    "Temperature in {location}: {temp}°C, humidity: {humidity}%."
                ],
                'summary': [
                    "Taking all locations together, the average is {avg_temp}°C.",
                    "The typical temperature right now is {avg_temp}°C.",
                    "If you average everything, it's {avg_temp}°C.",
                    "Region-wide, we're looking at {avg_temp}°C.",
                    "The mean temperature is {avg_temp}°C."
                ],
                'outro': [
                    "Want to know more?",
                    "Anything else?",
                    "What else would you like?",
                    "Need more details?",
                    "Something else?"
                ]
            },
            {
                'intro': [
                    "Sure thing! Here's the weather.",
                    "Got it! Checking weather now.",
                    "Weather info ready.",
                    "Let me see what's happening outside.",
                    "Here you go!"
                ],
                'location': [
                    "Over at {location}, we've got {temp}°C and {humidity}% humidity.",
                    "{location} reads {temp}°C, {humidity}% humidity.",
                    "The temperature at {location} is {temp}°C, humidity: {humidity}%.",
                    "{location} showing {temp} degrees and {humidity}% humidity.",
                    "It's {temp}°C in {location}, with the air at {humidity}% humidity."
                ],
                'summary': [
                    "On average, it's {avg_temp}°C everywhere.",
                    "The overall average temperature is {avg_temp}°C.",
                    "Put it all together and you get {avg_temp}°C.",
                    "Temperature average: {avg_temp}°C across the board.",
                    "Looking at everything, {avg_temp}°C is the average."
                ],
                'outro': [
                    "What else do you need?",
                    "Anything more?",
                    "Need something else?",
                    "What else can I find for you?",
                    "More questions?"
                ]
            },
            {
                'intro': [
                    "Here's the weather situation.",
                    "Weather data is in!",
                    "Let me break down the weather for you.",
                    "Okay, weather check complete.",
                    "Here's what I found."
                ],
                'location': [
                    "{location} is sitting at {temp}°C with {humidity}% humidity.",
                    "At {location}: temperature is {temp}°C, humidity is at {humidity}%.",
                    "{temp} degrees in {location}, {humidity}% humidity.",
                    "{location} reports {temp}°C and {humidity}% humidity.",
                    "Current conditions in {location}: {temp}°C, {humidity}% humid."
                ],
                'summary': [
                    "The temperature averages out to {avg_temp}°C.",
                    "Across all spots, it's roughly {avg_temp}°C.",
                    "Average temp for the area: {avg_temp}°C.",
                    "We're seeing {avg_temp}°C on average.",
                    "The general temperature is {avg_temp}°C."
                ],
                'outro': [
                    "What else would you like?",
                    "Anything else I can help with?",
                    "Need more info?",
                    "What else?",
                    "Something else you want to know?"
                ]
            },
            {
                'intro': [
                    "Weather update ready!",
                    "Here's how it looks.",
                    "Let me check that for you.",
                    "Alright, got the weather.",
                    "Here's what's happening outside."
                ],
                'location': [
                    "{location} has {temp}°C and it's {humidity}% humid.",
                    "In {location} right now: {temp}°C, {humidity}% humidity.",
                    "{temp}°C at {location}, moisture level {humidity}%.",
                    "{location}: {temp} degrees, {humidity}% humidity.",
                    "Temperature at {location} is {temp}°C, humidity at {humidity}%."
                ],
                'summary': [
                    "Overall average: {avg_temp}°C.",
                    "The mean temperature is {avg_temp}°C.",
                    "Averaging all the readings: {avg_temp}°C.",
                    "Region-wide average: {avg_temp}°C.",
                    "Temperature across all areas: {avg_temp}°C average."
                ],
                'outro': [
                    "Anything else?",
                    "What else can I get you?",
                    "Need anything more?",
                    "What else would you like to know?",
                    "More questions?"
                ]
            }
        ]
        
        #Templates for parking responses (ENGLISH - ALL PRESERVED)
        self.parking_templates_en = [
            {
                'intro': [
                    "Here's the parking situation right now.",
                    "Let me check parking for you.",
                    "Parking update ready!",
                    "Here's what I found for parking.",
                    "Got the parking info!"
                ],
                'location': [
                    "{location} has {free} spots available out of {total} ({percent}% free).",
                    "At {location}: {free} free spaces out of {total} total ({percent}%).",
                    "{location} shows {free}/{total} spots available, that's {percent}%.",
                    "{free} parking spots free at {location} out of {total} ({percent}%).",
                    "{location}: {free} available, {total} total capacity ({percent}% free)."
                ],
                'summary': [
                    "Overall, {total_free} spaces available out of {total_spots} total ({percent}%).",
                    "In total: {total_free}/{total_spots} spots free ({percent}%).",
                    "Across all locations: {total_free} free spaces, {total_spots} total ({percent}%).",
                    "Combined availability: {total_free} out of {total_spots} spots ({percent}%).",
                    "All parking areas: {total_free}/{total_spots} available ({percent}%)."
                ],
                'outro': [
                    "Need anything else?",
                    "What else can I help with?",
                    "Anything more?",
                    "What else?",
                    "More questions?"
                ]
            },
            {
                'intro': [
                    "Checking parking availability now.",
                    "Here's the current parking status.",
                    "Parking info coming up!",
                    "Let me see what's available.",
                    "Got it! Here's parking."
                ],
                'location': [
                    "{location} has {free} open spots (total: {total}, {percent}% available).",
                    "Right now at {location}: {free} free, {total} total, {percent}% open.",
                    "{free} spaces at {location}, capacity is {total} ({percent}%).",
                    "{location}: {free} available parking spots out of {total} ({percent}%).",
                    "At {location}, {free} out of {total} spots are free ({percent}%)."
                ],
                'summary': [
                    "Total across all areas: {total_free} free out of {total_spots} ({percent}%).",
                    "Combined: {total_free}/{total_spots} spots available ({percent}%).",
                    "All locations together: {total_free} free spaces ({percent}% of {total_spots}).",
                    "Overall: {total_free} available parking spots from {total_spots} total ({percent}%).",
                    "Grand total: {total_free}/{total_spots} free ({percent}%)."
                ],
                'outro': [
                    "Anything else?",
                    "Need more info?",
                    "What else would you like?",
                    "Something else?",
                    "More questions?"
                ]
            },
            {
                'intro': [
                    "Parking check done!",
                    "Here's what's available.",
                    "Let me tell you about parking.",
                    "Parking status ready.",
                    "Here you go!"
                ],
                'location': [
                    "{free} spots open at {location} (out of {total}, {percent}% free).",
                    "{location}: {free} available, {percent}% of {total} spots.",
                    "There are {free} free spaces at {location}, that's {percent}% of {total}.",
                    "{location} shows {free} open spots from {total} total ({percent}%).",
                    "{free} parking spaces free at {location} ({percent}% of {total})."
                ],
                'summary': [
                    "{total_free} total free spaces across all parking ({percent}% of {total_spots}).",
                    "All together: {total_free} available from {total_spots} spots ({percent}%).",
                    "{total_free} free spaces in total, {percent}% availability.",
                    "Combined total: {total_free}/{total_spots} free ({percent}%).",
                    "{total_free} spots available overall ({percent}% of {total_spots} total)."
                ],
                'outro': [
                    "What else?",
                    "Anything more you need?",
                    "Need something else?",
                    "What else can I find?",
                    "More info needed?"
                ]
            },
            {
                'intro': [
                    "Alright, here's parking.",
                    "Parking update for you.",
                    "Let me check that.",
                    "Here's the parking info.",
                    "Got the parking data!"
                ],
                'location': [
                    "{location} has {free} free spots, {total} capacity ({percent}%).",
                    "At {location}: {free}/{total} available ({percent}%).",
                    "{free} open spaces at {location} (capacity: {total}, {percent}% free).",
                    "{location}: {free} available spaces out of {total} ({percent}%).",
                    "{free} spots free at {location}, {percent}% of {total} total."
                ],
                'summary': [
                    "Altogether: {total_free} spaces free from {total_spots} ({percent}%).",
                    "Total parking: {total_free}/{total_spots} available ({percent}%).",
                    "{total_free} free spaces across everything ({percent}% of {total_spots}).",
                    "Overall availability: {total_free} out of {total_spots} ({percent}%).",
                    "{total_free} spaces available total, {percent}% free."
                ],
                'outro': [
                    "Need more?",
                    "What else would you like to know?",
                    "Anything else I can help with?",
                    "Something else?",
                    "More questions?"
                ]
            },
            {
                'intro': [
                    "Sure! Here's parking.",
                    "Parking check complete.",
                    "Let me get that for you.",
                    "Here's what I see.",
                    "Parking info ready!"
                ],
                'location': [
                    "{location}: {free} available out of {total} spots ({percent}% free).",
                    "{free} spaces open at {location}, {percent}% availability.",
                    "At {location}, {free} free parking spots ({total} total, {percent}%).",
                    "{location} has {free}/{total} available ({percent}%).",
                    "{free} open at {location} (out of {total}, {percent}% free)."
                ],
                'summary': [
                    "In total: {total_free} available spaces ({percent}% of {total_spots}).",
                    "Overall: {total_free}/{total_spots} free spots ({percent}%).",
                    "{total_free} spaces available across all parking ({percent}%).",
                    "Combined: {total_free} free from {total_spots} total ({percent}%).",
                    "All locations: {total_free} available, {percent}% free."
                ],
                'outro': [
                    "Anything else?",
                    "What else?",
                    "Need more details?",
                    "Something else you want?",
                    "More info?"
                ]
            }
        ]
        
        # Traffic templates ENGLISH
        self.traffic_templates_en = [
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
        
        # ========== GERMAN TEMPLATES==========
        # German Weather Templates
        self.weather_templates_de = [
            {
                'intro': [
                    "Hier ist das aktuelle Wetter draußen.",
                    "Lassen Sie mich das Wetter für Sie prüfen.",
                    "Hier ist das heutige Wetter.",
                    "Ich prüfe das Wetter jetzt...",
                    "Wetterinfos sind da!"
                ],
                'location': [
                    "In {location} sind es {temp}°C mit {humidity}% Luftfeuchtigkeit.",
                    "{location} zeigt {temp}°C und {humidity}% Luftfeuchtigkeit.",
                    "In {location}: {temp}°C, Feuchtigkeit bei {humidity}%.",
                    "{location} hat gerade {temp}°C, {humidity}% Luftfeuchtigkeit.",
                    "Es sind {temp}°C in {location} mit {humidity}% Luftfeuchtigkeit."
                ],
                'summary': [
                    "Die Durchschnittstemperatur über alle Bereiche beträgt {avg_temp}°C.",
                    "Insgesamt sind es etwa {avg_temp}°C in der Region.",
                    "Im Durchschnitt sind es: {avg_temp}°C.",
                    "Die allgemeine Temperatur liegt bei etwa {avg_temp}°C.",
                    "Über alle Standorte hinweg sehen wir durchschnittlich {avg_temp}°C."
                ],
                'outro': [
                    "Benötigen Sie noch etwas?",
                    "Womit kann ich sonst helfen?",
                    "Möchten Sie noch etwas wissen?",
                    "Sonst noch etwas?",
                    "Brauchen Sie mehr Informationen?"
                ]
            },
            {
                'intro': [
                    "Okay, hier ist das aktuelle Wetter.",
                    "Wetter-Update kommt gleich!",
                    "Lassen Sie mich Ihnen vom Wetter erzählen.",
                    "So sieht es draußen aus.",
                    "Wetterprüfung abgeschlossen!"
                ],
                'location': [
                    "{location}: {temp}°C, {humidity}% Luftfeuchtigkeit.",
                    "Gerade in {location} sind es {temp}°C, die Luftfeuchtigkeit liegt bei {humidity}%.",
                    "{temp}°C in {location}, Feuchtigkeitsniveau: {humidity}%.",
                    "{location} ist bei {temp}°C mit {humidity}% Feuchtigkeit in der Luft.",
                    "Temperatur in {location}: {temp}°C, Luftfeuchtigkeit: {humidity}%."
                ],
                'summary': [
                    "Wenn wir alle Standorte zusammennehmen, liegt der Durchschnitt bei {avg_temp}°C.",
                    "Die typische Temperatur gerade jetzt beträgt {avg_temp}°C.",
                    "Wenn Sie alles mitteln, sind es {avg_temp}°C.",
                    "Regionsweit betrachten wir {avg_temp}°C.",
                    "Die mittlere Temperatur beträgt {avg_temp}°C."
                ],
                'outro': [
                    "Möchten Sie mehr wissen?",
                    "Sonst noch etwas?",
                    "Was möchten Sie noch wissen?",
                    "Brauchen Sie weitere Details?",
                    "Etwas anderes?"
                ]
            },
            {
                'intro': [
                    "Klar! Hier ist das Wetter.",
                    "Verstanden! Prüfe Wetter jetzt.",
                    "Wetterinfos sind bereit.",
                    "Mal sehen, was draußen los ist.",
                    "Bitte schön!"
                ],
                'location': [
                    "Drüben in {location} haben wir {temp}°C und {humidity}% Luftfeuchtigkeit.",
                    "{location} zeigt {temp}°C, {humidity}% Luftfeuchtigkeit.",
                    "Die Temperatur in {location} beträgt {temp}°C, Feuchtigkeit: {humidity}%.",
                    "{location} zeigt {temp} Grad und {humidity}% Luftfeuchtigkeit.",
                    "Es sind {temp}°C in {location}, mit der Luft bei {humidity}% Feuchtigkeit."
                ],
                'summary': [
                    "Im Durchschnitt sind es überall {avg_temp}°C.",
                    "Die durchschnittliche Gesamttemperatur beträgt {avg_temp}°C.",
                    "Alles zusammengefasst ergibt {avg_temp}°C.",
                    "Temperaturdurchschnitt: {avg_temp}°C überall.",
                    "Betrachtet man alles, sind {avg_temp}°C der Durchschnitt."
                ],
                'outro': [
                    "Was brauchen Sie noch?",
                    "Noch etwas?",
                    "Brauchen Sie etwas anderes?",
                    "Was kann ich noch für Sie finden?",
                    "Weitere Fragen?"
                ]
            }
        ]
        
        # German Parking Templates
        self.parking_templates_de = [
            {
                'intro': [
                    "Hier ist die aktuelle Parksituation.",
                    "Lassen Sie mich das Parken für Sie prüfen.",
                    "Parkplatz-Update ist bereit!",
                    "Hier ist, was ich für Parkplätze gefunden habe.",
                    "Habe die Parkinfos!"
                ],
                'location': [
                    "{location} hat {free} freie Plätze von {total} ({percent}% frei).",
                    "Bei {location}: {free} freie Plätze von {total} insgesamt ({percent}%).",
                    "{location} zeigt {free}/{total} verfügbare Plätze, das sind {percent}%.",
                    "{free} Parkplätze frei bei {location} von {total} ({percent}%).",
                    "{location}: {free} verfügbar, {total} Gesamtkapazität ({percent}% frei)."
                ],
                'summary': [
                    "Insgesamt {total_free} Plätze verfügbar von {total_spots} insgesamt ({percent}%).",
                    "Insgesamt: {total_free}/{total_spots} Plätze frei ({percent}%).",
                    "Über alle Standorte: {total_free} freie Plätze, {total_spots} insgesamt ({percent}%).",
                    "Kombinierte Verfügbarkeit: {total_free} von {total_spots} Plätzen ({percent}%).",
                    "Alle Parkbereiche: {total_free}/{total_spots} verfügbar ({percent}%)."
                ],
                'outro': [
                    "Benötigen Sie noch etwas?",
                    "Womit kann ich sonst helfen?",
                    "Noch etwas?",
                    "Sonst noch etwas?",
                    "Weitere Fragen?"
                ]
            },
            {
                'intro': [
                    "Prüfe Parkverfügbarkeit jetzt.",
                    "Hier ist der aktuelle Parkstatus.",
                    "Parkinfos kommen gleich!",
                    "Mal sehen, was verfügbar ist.",
                    "Verstanden! Hier sind die Parkplätze."
                ],
                'location': [
                    "{location} hat {free} offene Plätze (gesamt: {total}, {percent}% verfügbar).",
                    "Gerade bei {location}: {free} frei, {total} insgesamt, {percent}% offen.",
                    "{free} Plätze bei {location}, Kapazität ist {total} ({percent}%).",
                    "{location}: {free} verfügbare Parkplätze von {total} ({percent}%).",
                    "Bei {location} sind {free} von {total} Plätzen frei ({percent}%)."
                ],
                'summary': [
                    "Gesamt über alle Bereiche: {total_free} frei von {total_spots} ({percent}%).",
                    "Kombiniert: {total_free}/{total_spots} Plätze verfügbar ({percent}%).",
                    "Alle Standorte zusammen: {total_free} freie Plätze ({percent}% von {total_spots}).",
                    "Insgesamt: {total_free} verfügbare Parkplätze von {total_spots} insgesamt ({percent}%).",
                    "Gesamtsumme: {total_free}/{total_spots} frei ({percent}%)."
                ],
                'outro': [
                    "Sonst noch etwas?",
                    "Brauchen Sie mehr Infos?",
                    "Was möchten Sie noch wissen?",
                    "Etwas anderes?",
                    "Weitere Fragen?"
                ]
            },
            {
                'intro': [
                    "Parkprüfung erledigt!",
                    "Hier ist, was verfügbar ist.",
                    "Lassen Sie mich Ihnen vom Parken erzählen.",
                    "Parkstatus bereit.",
                    "Bitte schön!"
                ],
                'location': [
                    "{free} Plätze offen bei {location} (von {total}, {percent}% frei).",
                    "{location}: {free} verfügbar, {percent}% von {total} Plätzen.",
                    "Es gibt {free} freie Plätze bei {location}, das sind {percent}% von {total}.",
                    "{location} zeigt {free} offene Plätze von {total} insgesamt ({percent}%).",
                    "{free} Parkplätze frei bei {location} ({percent}% von {total})."
                ],
                'summary': [
                    "{total_free} freie Plätze insgesamt über alle Parkplätze ({percent}% von {total_spots}).",
                    "Alles zusammen: {total_free} verfügbar von {total_spots} Plätzen ({percent}%).",
                    "{total_free} freie Plätze insgesamt, {percent}% Verfügbarkeit.",
                    "Kombinierte Summe: {total_free}/{total_spots} frei ({percent}%).",
                    "{total_free} Plätze insgesamt verfügbar ({percent}% von {total_spots} gesamt)."
                ],
                'outro': [
                    "Sonst noch etwas?",
                    "Brauchen Sie noch etwas?",
                    "Brauchen Sie etwas anderes?",
                    "Was kann ich noch finden?",
                    "Mehr Infos nötig?"
                ]
            }
        ]
        
        # German Traffic Templates
        self.traffic_templates_de = [
            {
                'intro': [
                    "Hier sehen die aktuellen Verkehrsbedingungen aus.",
                    "Lassen Sie mich Ihnen ein Update zur Verkehrslage geben.",
                    "Hier ist Ihr Verkehrsfluss-Update basierend auf Daten von Kreuzungsüberwachungssystemen.",
                    "Lassen Sie mich aufschlüsseln, was gerade auf den Straßen passiert.",
                    "Hier ist, was die Verkehrsüberwachungssysteme melden."
                ],
                'location': [
                    "Bei {location} erfassen Verkehrssensoren {vehicles_in} einfahrende Fahrzeuge und {vehicles_out} ausfahrende Fahrzeuge. Die Durchschnittsgeschwindigkeit durch diesen Bereich beträgt {speed} km/h. Zusätzlich zeigen Fußgängerzähler {pedestrians} Personen, die durch den Bereich gehen, während Radfahrerdetektionssysteme {cyclists} Radfahrer erfassen, die die Kreuzung passieren.",
                    "Die Verkehrsüberwachungsstation bei {location} meldet {vehicles_in} einfahrende und {vehicles_out} ausfahrende Fahrzeuge. Die Fahrzeuggeschwindigkeiten betragen durchschnittlich {speed} km/h durch diese Kreuzung. Der Bereich beherbergt auch {pedestrians} Fußgänger und {cyclists} Radfahrer, was zeigt, dass dies ein multimodaler Verkehrsknotenpunkt ist.",
                    "📍 Aktuelle Daten von {location} zeigen {vehicles_in} Fahrzeuge, die in die Kreuzung einfahren, während {vehicles_out} Fahrzeuge ausfahren. Der Verkehr bewegt sich mit einer Durchschnittsgeschwindigkeit von {speed} km/h. Fußgängersensoren zeigen {pedestrians} Personen, die im Bereich gehen, und Fahrrad-Zähler zeigen {cyclists} Radfahrer, die die Kreuzung nutzen.",
                    "Der Verkehrsfluss bei {location} zeigt {vehicles_in} einfahrende und {vehicles_out} ausfahrende Fahrzeuge. Die Geschwindigkeitssensoren zeigen eine Durchschnittsgeschwindigkeit von {speed} km/h für die Fahrzeugbewegung. Fußgängerdetektionssysteme erfassen {pedestrians} gehende Personen, während die Radinfrastruktur {cyclists} Radfahrer zeigt, die diese Kreuzung aktiv nutzen.",
                    "Die Kreuzung bei {location} verarbeitet {vehicles_in} einfahrende Fahrzeuge gegen {vehicles_out} ausfahrende Fahrzeuge. Geschwindigkeitsmessungen zeigen, dass sich der Verkehr durchschnittlich mit {speed} km/h bewegt. Die Überwachungssysteme erfassen auch {pedestrians} Fußgänger, die sich durch den Bereich bewegen, und {cyclists} Radfahrer, die die Kreuzungsinfrastruktur nutzen."
                ],
                'summary': [
                    "Bei Betrachtung der Verkehrsdaten von allen Überwachungsstandorten beträgt die durchschnittliche Fahrzeuggeschwindigkeit im gesamten Netzwerk {avg_speed} km/h.",
                    "Wenn ich die Geschwindigkeiten von allen Verkehrsüberwachungspunkten berechne, ergibt sich der netzwerkweite Durchschnitt von {avg_speed} km/h.",
                    "Der mathematische Durchschnitt der Fahrzeuggeschwindigkeiten über alle überwachten Standorte zeigt {avg_speed} km/h.",
                    "Die Durchschnittsberechnung der Geschwindigkeitsmessungen von allen Verkehrssensoren ergibt {avg_speed} km/h über das überwachte Netzwerk.",
                    "Die mittlere Geschwindigkeitsberechnung über alle Verkehrsüberwachungsstationen zeigt {avg_speed} km/h."
                ],
                'outro': [
                    "Was möchten Sie sonst noch über den Verkehr wissen?",
                    "Gibt es noch etwas über die Verkehrsbedingungen, das Sie wissen möchten?",
                    "Was möchten Sie noch wissen?",
                    "Benötigen Sie weitere Verkehrsinformationen?",
                    "Womit kann ich Ihnen sonst helfen?"
                ]
            },
            {
                'intro': [
                    "Ich habe Daten von Kreuzungssensoren und Fahrzeugdetektionssystemen im gesamten Netzwerk verarbeitet.",
                    "Hier ist Ihre detaillierte Verkehrsanalyse basierend auf Echtzeit-Sensordaten von Fahrzeugzähl- und Geschwindigkeitsdetektionssystemen."
                ],
                'location': [
                    "Das Verkehrsmanagementsystem bei {location} meldet {vehicles_in} einfahrende und {vehicles_out} ausfahrende Fahrzeuge. Die Geschwindigkeitserkennung zeigt Fahrzeuge, die sich mit {speed} km/h bewegen. Die Kreuzung bedient mehrere Transportmodi mit {pedestrians} Fußgängern und {cyclists} Radfahrern, die den Bereich nutzen.",
                    "{location} verarbeitet derzeit {vehicles_in} einfahrende Fahrzeuge mit {vehicles_out} ausfahrenden Fahrzeugen. Die Geschwindigkeitsüberwachung zeigt eine durchschnittliche Fahrzeuggeschwindigkeit von {speed} km/h. Fußgängerzählsysteme zeigen {pedestrians} Personen zu Fuß, während die Fahrrad-Erkennung {cyclists} Radfahrer erfasst, die die Kreuzung aktiv nutzen.",
                    "Verkehrsdaten von {location} zeigen {vehicles_in} einfahrende Fahrzeuge gegen {vehicles_out} ausfahrende Fahrzeuge. Fahrzeuggeschwindigkeitssensoren zeigen eine durchschnittliche Bewegung von {speed} km/h. Der Bereich beherbergt auch nicht-motorisierten Verkehr mit {pedestrians} Fußgängern und {cyclists} Radfahrern, die durch die Kreuzung fahren."
                ],
                'summary': [
                    "Die kombinierte Verkehrsanalyse zeigt eine Durchschnittsgeschwindigkeit von {avg_speed} km/h über alle überwachten Kreuzungen. Diese Geschwindigkeitsmetrik repräsentiert die Gesamtleistung des Verkehrsflusses im gesamten Netzwerk.",
                    "Wenn ich Geschwindigkeitsdaten von allen Verkehrsüberwachungspunkten analysiere, liegt der Netzwerk-Durchschnitt bei {avg_speed} km/h."
                ],
                'outro': [
                    "Was möchten Sie sonst noch wissen?",
                    "Gibt es noch etwas über den Verkehr, das Sie wissen möchten?",
                    "Was möchten Sie noch wissen?"
                ]
            },
            {
                'intro': [
                    "Ich habe die neuesten Verkehrsflussdaten von Kreuzungsüberwachungssystemen entschlüsselt.",
                    "Ihr Verkehrsanalysebericht ist bereit.",
                    "Lassen Sie mich die aktuellen Transportdynamiken über alle Kreuzungspunkte aufschlüsseln."
                ],
                'location': [
                    "Verkehrssensoren bei {location} erfassen {vehicles_in} einfahrende Fahrzeuge, während gleichzeitig {vehicles_out} ausfahrende Fahrzeuge aufgezeichnet werden. Geschwindigkeitsmesssysteme zeigen Fahrzeuge, die mit {speed} km/h fahren. Die Kreuzungsinfrastruktur unterstützt auch {pedestrians} Fußgänger, die sich durch den Bereich bewegen, und {cyclists} Radfahrer, die dedizierte Radwege oder gemeinsame Räume nutzen.",
                    "Der aktuelle Verkehrsfluss bei {location} zeigt {vehicles_in} einfahrende Fahrzeuge im Vergleich zu {vehicles_out} ausfahrenden Fahrzeugen. Geschwindigkeitsdetektionsgeräte messen {speed} km/h für die Fahrzeugbewegung. Fußgängerüberwachungssysteme erfassen {pedestrians} Personen, die durch die Kreuzung gehen, während Fahrradzähler {cyclists} Radfahrer zeigen, die das Verkehrsnetzwerk aktiv nutzen.",
                    "Kreuzungsüberwachung bei {location} zeigt {vehicles_in} einfahrende Fahrzeuge mit {vehicles_out} ausfahrenden Fahrzeugen. Die durchschnittliche Fahrzeuggeschwindigkeit wird mit {speed} km/h gemessen. Die multimodale Natur dieser Kreuzung ist offensichtlich mit {pedestrians} Fußgängern und {cyclists} Radfahrern, die sich den Verkehrsraum teilen."
                ],
                'summary': [
                    "Die statistische Analyse der Geschwindigkeitsmessungen von allen Verkehrsüberwachungsstandorten ergibt einen Durchschnitt von {avg_speed} km/h über das Netzwerk. Diese Geschwindigkeitsmetrik bietet Einblick in die gesamten Verkehrsflussdynamiken und potenzielle Staumuster.",
                    "Die aggregierten Geschwindigkeitsdaten von allen Kreuzungsüberwachungspunkten zeigen {avg_speed} km/h als netzwerkweiten Durchschnitt."
                ],
                'outro': [
                    "Was möchten Sie sonst noch wissen?",
                    "Gibt es noch etwas, das Sie wissen müssen?",
                    "Was möchten Sie noch wissen?"
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
        
        # German Location-specific parking templates
        self.location_specific_templates_de = {
            'intro': [
                "Hier ist die aktuelle Parksituation bei {location}:",
                "Lassen Sie mich die Parkverfügbarkeit bei {location} prüfen:",
                "Aktueller Parkstatus für {location}:",
                "Hier ist, was ich für Parkplätze bei {location} gefunden habe:"
            ],
            'single_location': [
                "🅿️ Bei {location} gibt es {free} verfügbare Parkplätze von {total} Gesamtplätzen. Das sind {percent}% Verfügbarkeit.",
                "🚗 {location} hat derzeit {free} freie Plätze mit einer Gesamtkapazität von {total} Plätzen ({percent}% verfügbar).",
                "📍 Die Parkeinrichtung bei {location} zeigt {free} verfügbare Plätze von {total} insgesamt ({percent}% Verfügbarkeit).",
                "🚙 {location} meldet {free} offene Parkplätze von insgesamt {total} Plätzen - {percent}% Verfügbarkeit gerade jetzt."
            ],
            'not_found': [
                "Ich konnte keine Parkdaten für {location} finden. Lassen Sie mich Ihnen stattdessen alle verfügbaren Parkstandorte zeigen:",
                "Keine spezifischen Daten für {location} gefunden. Hier ist die aktuelle Parksituation an allen überwachten Standorten:"
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
        
        # German Weather-specific location templates
        self.weather_location_specific_templates_de = {
            'intro': [
                "Hier ist das aktuelle Wetter bei {location}:",
                "Lassen Sie mich die Wetterbedingungen bei {location} prüfen:",
                "Aktueller Wetterstatus für {location}:",
                "Hier ist, was ich für das Wetter bei {location} gefunden habe:"
            ],
            'single_location': [
                "🌡️ Bei {location} beträgt die Temperatur {temp}°C mit {humidity}% Luftfeuchtigkeit.",
                "📍 {location} ist derzeit {temp}°C mit einer Luftfeuchtigkeit von {humidity}%.",
                "🌤️ Wetterbedingungen bei {location}: {temp}°C Temperatur und {humidity}% Luftfeuchtigkeit.",
                "☁️ {location} meldet gerade {temp}°C und {humidity}% Luftfeuchtigkeit."
            ],
            'not_found': [
                "Ich konnte keine Wetterdaten für {location} finden. Lassen Sie mich Ihnen stattdessen alle verfügbaren Wetterstandorte zeigen:",
                "Keine spezifischen Daten für {location} gefunden. Hier ist die aktuelle Wettersituation an allen überwachten Standorten:"
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
        
        # German Traffic-specific location templates
        self.traffic_location_specific_templates_de = {
            'intro': [
                "Hier ist die aktuelle Verkehrssituation bei {location}:",
                "Lassen Sie mich die Verkehrsbedingungen bei {location} prüfen:",
                "Aktueller Verkehrsstatus für {location}:",
                "Hier ist, was ich für den Verkehr bei {location} gefunden habe:"
            ],
            'single_location': [
                "🚦 Bei {location} fahren {vehicles_in} Fahrzeuge ein und {vehicles_out} Fahrzeuge aus mit einer Durchschnittsgeschwindigkeit von {speed} km/h. Ich sehe auch {pedestrians} Fußgänger und {cyclists} Radfahrer im Bereich.",
                "🚗 {location} hat derzeit {vehicles_in} einfahrende und {vehicles_out} ausfahrende Fahrzeuge, die sich mit durchschnittlich {speed} km/h bewegen. Die Kreuzung bedient {pedestrians} Fußgänger und {cyclists} Radfahrer.",
                "📍 Verkehrsfluss bei {location}: {vehicles_in} Fahrzeuge rein, {vehicles_out} Fahrzeuge raus, Durchschnittsgeschwindigkeit {speed} km/h, plus {pedestrians} Fußgänger und {cyclists} Radfahrer.",
                "🛣️ {location} meldet {vehicles_in} einfahrende Fahrzeuge, {vehicles_out} ausfahrende Fahrzeuge bei {speed} km/h, mit {pedestrians} Fußgängern und {cyclists} Radfahrern, die die Kreuzung nutzen."
            ],
            'speed_focused': [
                "🚦 Die Verkehrsgeschwindigkeit bei {location} beträgt {speed} km/h.",
                "🏃 Fahrzeuge bewegen sich mit {speed} km/h bei {location}.",
                "📊 Die Durchschnittsgeschwindigkeit bei {location} beträgt {speed} km/h."
            ],
            'pedestrians_focused': [
                "🚶 Es gibt {pedestrians} Fußgänger bei {location}.",
                "👥 {location} hat {pedestrians} Fußgänger im Bereich.",
                "🚶‍♂️ Fußgängerzahl bei {location}: {pedestrians} Personen."
            ],
            'cyclists_focused': [
                "🚴 Es gibt {cyclists} Radfahrer bei {location}.",
                "🚲 {location} hat {cyclists} Radfahrer, die die Kreuzung nutzen.",
                "🚴‍♂️ Radfahrerzahl bei {location}: {cyclists} Personen."
            ],
            'vehicles_focused': [
                "🚗 Fahrzeugfluss bei {location}: {vehicles_in} einfahrend, {vehicles_out} ausfahrend.",
                "🚙 {location} hat {vehicles_in} einfahrende und {vehicles_out} ausfahrende Fahrzeuge.",
                "📈 Verkehrsfluss bei {location}: {vehicles_in} rein, {vehicles_out} raus."
            ]
        }
        
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
    def generate_location_specific_traffic_response(self, data: List[Dict[str, Any]], requested_location: str, original_question: str, language: str = 'en') -> str:
        """Generate response for a specific traffic location request"""
        if not data:
            if language == 'de':
                return f"Ich konnte keine Verkehrsdaten für {requested_location} finden. Bitte versuchen Sie es später noch einmal!"
            return f"I couldn't find traffic data for {requested_location} right now. Please try again later!"
        
        try:
            if len(data) == 1:
                item = data[0]
                location_name = self.format_location_name(item.get('location_name', item.get('id', requested_location)))
                if ':' in location_name and 'Junction:' in location_name:
                    location_name = location_name.split(':')[-1]
                    location_name = re.sub(r'(?<!^)(?=[A-Z])', ' ', location_name)
                speed = item.get('avgSpeed', 0)
                vehicles_in = item.get('vehiclesIn', 0)
                vehicles_out = item.get('vehiclesOut', 0)
                pedestrians = item.get('pedestrians', 0)
                cyclists = item.get('cyclists', 0)
                question_lower = original_question.lower()
                
                # German-specific keywords
                german_pedestrian_words = ['fußgänger', 'fussgänger', 'gehen', 'passant']
                german_cyclist_words = ['radfahrer', 'fahrrad', 'rad', 'radeln']
                german_speed_words = ['geschwindigkeit', 'tempo', 'schnell', 'langsam']
                german_vehicle_words = ['fahrzeug', 'auto', 'fluss', 'einfahren', 'ausfahren']
                
                # Check for focused responses
                is_pedestrian_query = any(word in question_lower for word in ['pedestrian', 'walking', 'foot', 'people walking'] + german_pedestrian_words)
                is_cyclist_query = any(word in question_lower for word in ['cyclist', 'cycling', 'bike', 'bicycle'] + german_cyclist_words)
                is_speed_query = any(word in question_lower for word in ['speed', 'fast', 'slow', 'km/h', 'mph'] + german_speed_words)
                is_vehicle_query = any(word in question_lower for word in ['vehicle', 'car', 'flow', 'enter', 'exit', 'incoming', 'outgoing'] + german_vehicle_words)
                
                templates = self.traffic_location_specific_templates_de if language == 'de' else self.traffic_location_specific_templates
                
                if is_pedestrian_query and not (is_cyclist_query or is_speed_query or is_vehicle_query):
                    response = random.choice(templates['pedestrians_focused']).format(location=location_name, pedestrians=pedestrians)
                    return response
                elif is_cyclist_query and not (is_pedestrian_query or is_speed_query or is_vehicle_query):
                    response = random.choice(templates['cyclists_focused']).format(location=location_name, cyclists=cyclists)
                    return response
                elif is_speed_query and not (is_pedestrian_query or is_cyclist_query or is_vehicle_query):
                    response = random.choice(templates['speed_focused']).format(location=location_name, speed=speed)
                    return response
                elif is_vehicle_query and not (is_pedestrian_query or is_cyclist_query or is_speed_query):
                    response = random.choice(templates['vehicles_focused']).format(location=location_name, vehicles_in=vehicles_in, vehicles_out=vehicles_out)
                    return response
                else:
                    intro = random.choice(templates['intro']).format(location=location_name)
                    status = self.get_traffic_status(speed)
                    emoji = random.choice(self.traffic_emojis[status])
                    response_text = random.choice(templates['single_location']).format(
                        location=location_name, speed=speed, vehicles_in=vehicles_in, 
                        vehicles_out=vehicles_out, pedestrians=pedestrians, cyclists=cyclists
                    )
    
                    return f"{intro} {emoji} {response_text}"
            else:
                return self.generate_traffic_response(data, original_question, language)
        except Exception as e:
            print(f"Error in generate_location_specific_traffic_response: {e}")
            if language == 'de':
                return f"Ich habe einige Verkehrsdaten für {requested_location} gefunden, hatte aber Probleme beim Formatieren der Antwort."
            return f"I found some traffic data for {requested_location} but had trouble formatting the response."

    def generate_location_specific_weather_response(self, data: List[Dict[str, Any]], requested_location: str, original_question: str, language: str = 'en') -> str:
        """Generate response for a specific weather location request"""
        if not data:
            if language == 'de':
                return f"Ich konnte keine Wetterdaten für {requested_location} finden. Bitte versuchen Sie es später noch einmal!"
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
                
                templates = self.weather_location_specific_templates_de if language == 'de' else self.weather_location_specific_templates
                intro = random.choice(templates['intro']).format(location=location_name)
                response_text = random.choice(templates['single_location']).format(
                    location=location_name,
                    temp=temp,
                    humidity=humidity
                )
                
                return f"{intro} {emoji} {response_text}"
            else:
                return self.generate_weather_response(data, original_question, language)
        except Exception as e:
            print(f"Error in generate_location_specific_weather_response: {e}")
            if language == 'de':
                return f"Ich habe einige Wetterdaten für {requested_location} gefunden, hatte aber Probleme beim Formatieren der Antwort."
            return f"I found some weather data for {requested_location} but had trouble formatting the response."
            
    def generate_location_specific_parking_response(self, data: List[Dict[str, Any]], requested_location: str, original_question: str, language: str = 'en') -> str:
        """Generate response for a specific location request"""
        if not data:
            if language == 'de':
                return f"Ich konnte keine Parkdaten für {requested_location} finden. Bitte versuchen Sie es später noch einmal!"
            return f"I couldn't find parking data for {requested_location} right now. Please try again later!"
        
        try:
            if len(data) == 1:
                item = data[0]
                location_name = self.format_location_name(item.get('location_name', item.get('id', requested_location)))
                free = item.get('freeSpaces', 0)
                total = item.get('totalSpaces', 0)
                percent = round((free / total * 100), 1) if total > 0 else 0
                
                templates = self.location_specific_templates_de if language == 'de' else self.location_specific_templates
                intro = random.choice(templates['intro']).format(location=location_name)
                response_text = random.choice(templates['single_location']).format(
                    location=location_name,
                    free=free,
                    total=total,
                    percent=percent
                )
                
                return f"{intro} {response_text}"
            else:
                return self.generate_parking_response(data, original_question, language)
        except Exception as e:
            print(f"Error in generate_location_specific_parking_response: {e}")
            if language == 'de':
                return f"Ich habe einige Daten für {requested_location} gefunden, hatte aber Probleme beim Formatieren der Antwort."
            return f"I found some data for {requested_location} but had trouble formatting the response."
    
    def generate_weather_response(self, data: List[Dict[str, Any]], original_question: str, language: str = 'en') -> str:
        if not data:
            if language == 'de':
                return "😔 Ich konnte gerade keine Wetterdaten finden. Bitte versuchen Sie es später noch einmal!"
            return "😔 I couldn't find any weather data right now. Please try again later!"
            
        templates = self.weather_templates_de if language == 'de' else self.weather_templates_en
        template = random.choice(templates)
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
            
            location_responses.append(emoji + " " + location_text)
        
        if len(location_responses) > 1:
            connectors = [", ", " und " if language == 'de' else " and ", ", außerdem " if language == 'de' else ", also ", ", plus "]
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
    
    def generate_parking_response(self, data: List[Dict[str, Any]], original_question: str, language: str = 'en') -> str:
        if not data:
            if language == 'de':
                return "🚫 Momentan keine Parkdaten verfügbar. Versuchen Sie es bald noch einmal!"
            return "🚫 No parking data available at the moment. Try again soon!"
            
        templates = self.parking_templates_de if language == 'de' else self.parking_templates_en
        template = random.choice(templates)
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
            
            location_responses.append(emoji + " " + location_text)
        response += "; ".join(location_responses)
        response += ". " + random.choice(template['summary']).format(
            total_free=total_free,
            total_spots=total_spots,
            percent=overall_percent
        )
        response += " " + random.choice(template['outro'])
        return response
    
    def generate_traffic_response(self, data: List[Dict[str, Any]], original_question: str, language: str = 'en') -> str:
        """Generate traffic response from data"""
        if not data:
            if language == 'de':
                return "🚦 Momentan keine Verkehrsdaten verfügbar. Schauen Sie später noch einmal vorbei!"
            return "🚦 No traffic data available right now. Check back later!"
            
        templates = self.traffic_templates_de if language == 'de' else self.traffic_templates_en
        template = random.choice(templates)
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
            location_responses.append(emoji + " " + location_text)
        
        separators = ["; ", " | ", " — ", ", während " if language == 'de' else ", while "]
        response += location_responses[0]
        for i in range(1, len(location_responses)):
            response += random.choice(separators) + location_responses[i]
        response += ". " + random.choice(template['summary']).format(avg_speed=avg_speed)
        response += " " + random.choice(template['outro'])
        return response
    
    ###generate appropriate response based on entity type with location awareness 
    def generate_response(self, entity_type: str, data: List[Dict[str, Any]], original_question: str, requested_location: Optional[str] = None, language: str = 'en') -> str:
        try:
            print(f"DEBUG: generate_response called with entity_type={entity_type}, data_length={len(data) if data else 0}, requested_location={requested_location}, language={language}")
            
            if entity_type == 'WeatherObserved':
                if requested_location and len(data) == 1:
                    return self.generate_location_specific_weather_response(data, requested_location, original_question, language)
                else:
                    return self.generate_weather_response(data, original_question, language)
            elif entity_type == 'ParkingSpot':
                if requested_location and len(data) == 1:
                    return self.generate_location_specific_parking_response(data, requested_location, original_question, language)
                else:
                    return self.generate_parking_response(data, original_question, language)
            elif entity_type == 'Traffic':
                print(f"DEBUG: Traffic entity detected. requested_location={requested_location}, data_length={len(data)}")
                if requested_location and len(data) == 1:
                    print(f"DEBUG: Using location-specific traffic response")
                    return self.generate_location_specific_traffic_response(data, requested_location, original_question, language)
                else:
                    print(f"DEBUG: Using general traffic response")
                    return self.generate_traffic_response(data, original_question, language)
            else:
                if language == 'de':
                    return "Ich habe einige Daten gefunden, bin mir aber nicht sicher, wie ich sie interpretieren soll. Können Sie anders fragen?"
                return "I found some data but I'm not sure how to interpret it. Can you try asking differently?"
        except Exception as e:
            print(f"Error in generate_response: {e}")
            if language == 'de':
                return f"Ich habe die angeforderten Daten gefunden, aber es gab einen Fehler beim Formatieren der Antwort. Bitte versuchen Sie es noch einmal."
            return f"I found the data you requested, but encountered an error while formatting the response. Please try asking again."

class SimpleFIWARETester:
    """location-aware response generation with multilingual support"""
    
    def __init__(self, fiware_url, api_key):
        self.fiware_url = fiware_url
        self.api_key = api_key
        self.translator = SimpleFIWARERuleBasedTranslator()
        self.response_generator = RuleBasedResponseGenerator()
        self.language_detector = LanguageDetector()

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

    def process_natural_query(self, natural_query, selected_language='en'):
        """Enhanced pipeline with language detection, validation, and location awareness"""
        print(f"Processing: {natural_query} (selected language: {selected_language})")
        
        # Detect actual language of the query
        detected_language = self.language_detector.detect(natural_query)
        print(f"Detected language: {detected_language}")
        
        # Check if detected language matches selected language
        if detected_language != selected_language:
            error_messages = {
                'en': "Please ask your question in English, as you've selected English as your language.",
                'de': "Bitte stellen Sie Ihre Frage auf Deutsch, da Sie Deutsch als Sprache ausgewählt haben."
            }
            return {
                "success": False,
                "message": error_messages.get(selected_language, error_messages['en']),
                "language_mismatch": True
            }
        
        try:
            requested_location = self.translator.extract_location_from_query(natural_query, selected_language)
            translation_result = self.translator.translate(natural_query, selected_language)
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
                
                # Generate response with language support
                explanation = self.response_generator.generate_response(
                    entity_type, 
                    result['data'], 
                    natural_query,
                    requested_location,
                    selected_language  # Pass language parameter
                )
                return {
                    "success": True,
                    "message": explanation,
                    "data": result["data"],
                    "language": selected_language,
                    "debug_info": {
                        "fiware_query": fiware_query,
                        "fallback_used": fallback_query is not None,
                        "data_count": len(result['data']) if isinstance(result['data'], list) else 0,
                        "entity_type": entity_type,
                        "requested_location": requested_location,
                        "detected_language": detected_language,
                        "selected_language": selected_language
                    }
                }
            else:
                error_emojis = ['😔', '😕', '🤷', '😅', '🙈']
                error_messages = {
                    'en': [
                        f"{random.choice(error_emojis)} I couldn't fetch the data right now. Please try again in a moment!",
                        f"{random.choice(error_emojis)} Oops! Something went wrong. Let me try again in a bit!",
                        f"{random.choice(error_emojis)} The data seems to be unavailable at the moment. Try again soon!",
                        f"{random.choice(error_emojis)} Having trouble connecting right now. Give it another shot!"
                    ],
                    'de': [
                        f"{random.choice(error_emojis)} Ich konnte die Daten gerade nicht abrufen. Bitte versuchen Sie es gleich noch einmal!",
                        f"{random.choice(error_emojis)} Hoppla! Etwas ist schiefgelaufen. Lassen Sie mich es gleich noch einmal versuchen!",
                        f"{random.choice(error_emojis)} Die Daten scheinen momentan nicht verfügbar zu sein. Versuchen Sie es bald noch einmal!",
                        f"{random.choice(error_emojis)} Verbindungsprobleme gerade. Versuchen Sie es noch einmal!"
                    ]
                }
                
                return {
                    "success": False,
                    "message": random.choice(error_messages.get(selected_language, error_messages['en'])),
                    "language": selected_language,
                    "debug_info": {
                        "fiware_query": fiware_query,
                        "fallback_query": fallback_query,
                        "error": result.get('error', 'Unknown error'),
                        "error_message": result.get('message', 'No error message'),
                        "requested_location": requested_location,
                        "detected_language": detected_language,
                        "selected_language": selected_language
                    }
                }
        except Exception as e:
            print(f"Error in process_natural_query: {e}")
            print(f"Query was: {natural_query}")
            error_messages = {
                'en': f"🤖 Sorry, I encountered an error while processing your request: {str(e)}",
                'de': f"🤖 Entschuldigung, ich bin auf einen Fehler gestoßen beim Verarbeiten Ihrer Anfrage: {str(e)}"
            }
            return {
                "success": False,
                "message": error_messages.get(selected_language, error_messages['en']),
                "language": selected_language,
                "debug_info": {
                    "error": "Processing Exception",
                    "error_message": str(e),
                    "query": natural_query,
                    "selected_language": selected_language
                }
            }


# Setup Flask
app = Flask(__name__)

# Start chatbot
chatbot = SimpleFIWARETester(os.environ["FIWARE_URL"], os.environ.get("FIWARE_API_KEY", ""))

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.get_json()
        user_message = data.get('message', '').strip()
        selected_language = data.get('language', 'en')  # Get language from request
        
        if not user_message:
            messages = {
                'en': 'Please enter a message. 💬',
                'de': 'Bitte geben Sie eine Nachricht ein. 💬'
            }
            return jsonify({
                'success': False,
                'message': messages.get(selected_language, messages['en'])
            })
        result = chatbot.process_natural_query(user_message, selected_language)
        response_data = {
            'success': result['success'],
            'message': result['message'],
            'timestamp': datetime.now().strftime('%H:%M'),
            'language_mismatch': result.get('language_mismatch', False)
        }
        
        if 'debug_info' in result:
            response_data['debug'] = result['debug_info']
        
        return jsonify(response_data)
        
    except Exception as e:
        print(f"Error processing chat: {e}")
        error_emojis = ['🤖', '⚡', '🔧', '🛠️']
        # Try to get language, default to English if not available
        selected_language = request.get_json().get('language', 'en') if request.get_json() else 'en'
        error_messages = {
            'en': f'{random.choice(error_emojis)} Sorry, I encountered an error while processing your request. Please try again!',
            'de': f'{random.choice(error_emojis)} Entschuldigung, ich bin auf einen Fehler gestoßen. Bitte versuchen Sie es noch einmal!'
        }
        return jsonify({
            'success': False,
            'message': error_messages.get(selected_language, error_messages['en']),
            'timestamp': datetime.now().strftime('%H:%M'),
            'debug': {'error': str(e)}
        })

if __name__ == '__main__':
    print("Starting Flask server")
    app.run(debug=False, host='0.0.0.0', port=5000)
