# Eco Search Engine Prototype

This project demonstrates how to overcome missing structured product attributes using free text search and intent extraction.

The system combines:

- Keyword-based detection
- LLM-based classification

to identify environmentally friendly products from unstructured product descriptions.

## Features

- Hybrid keyword + LLM filtering
- Simple Streamlit search interface
- No structured eco-friendly field required

## Run locally

Create virtual environment:
python3 -m venv venv
source venv/bin/activate

Install dependencies:
pip install -r requirements.txt

Run the app:
streamlit run app.py

## Example Query
çevre dostu

The system will analyze product descriptions and retrieve relevant items.