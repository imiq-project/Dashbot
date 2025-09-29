# Dashbot v1.0

A conversational interface for smart city dashboards that lets users ask natural language questions about real-time city data. Currently it supports only English, German will be supported really soon.

## What it does

Besides clicking through dashboard widgets, users can simply ask:
- "What's the temperature at Science Hub?"
- "Are there parking spaces available?"
- "How's traffic at FacultyCS?"

Dashbot translates these questions into FIWARE API queries and responds in natural language with current data from city sensors.

## Current capabilities

**Weather data**: Temperature and humidity readings from multiple city locations
**Parking information**: Real-time availability at monitored parking facilities  
**Traffic conditions**: Vehicle flow, speed, pedestrian and cyclist counts at intersections

**Supported locations**: Science Hub, Faculty CS, North Park, Science Harbor, Uni Mensa, Library, Welcome Center, Geschwister Park

## Technical approach

This version uses a rule-based dialogue system that:
- Matches keywords to determine what data the user wants (weather/parking/traffic)
- Extracts specific locations mentioned in queries
- Generates FIWARE-QL API calls to fetch real-time data
- Formats responses using templated natural language

No LLMs - just pattern matching and structured responses.

## Quick start

```bash
pip install -r requirements.txt
python app.py
# Visit http://localhost:5000
```

## Integration options

**Widget**: Copy files from `integration/` folder into the dashboard  

## Data source

Connects to FIWARE Context Broker at `https://imiq-public.et.uni-magdeburg.de/api/orion` for real-time city sensor data.

## What's next
- Integration with many more city data sources
- Machine learning for better query understanding
- LLMs for better language generation
- Support for more complex questions
- Understand how different city systems connect and influence each other using KG and provide predictive insights and actionable recommendations
- Interactive data visualizations alongside the conversational answers 
- Zoom in when specific locations are asked
