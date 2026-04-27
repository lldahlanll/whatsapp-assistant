import google.generativeai as genai
import os

# Set API Key kamu
genai.configure(api_key="AIzaSyDddtKJV3lJhdmI8XQ2rIedFL7S5bjUQXk")

# List semua model yang tersedia
for m in genai.list_models():
    if 'generateContent' in m.supported_generation_methods:
        print(f"Model Name: {m.name}")
        # print(f"Display Name: {m.display_name}")
        # print(f"Description: {m.description}")
        # print("-" * 30)