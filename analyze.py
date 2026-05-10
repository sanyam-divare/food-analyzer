# Food Analyzer - AI powered calorie tracker
# Author: Sanyam
# Started: May 2026

import os
import json
from datetime import datetime

def analyze_image(image_path):
    """
    Takes a food image and returns detected foods
    Later: this will connect to local AI model
    """
    print(f"Analyzing image: {image_path}")
    # TODO: connect to Ollama + LLaVA/Gemma3
    pass

def calculate_calories(foods):
    """
    Takes a list of foods and returns total calories
    """
    # TODO: look up each food in calories.py
    total = 0
    return total

def save_to_log(foods, calories):
    """
    Saves meal analysis to a local JSON log file
    """
    entry = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "foods": foods,
        "calories": calories
    }
    # TODO: save to meals_log.json
    print(f"Logged: {entry}")

def main():
    print("🍽️ Food Analyzer Starting...")
    image_path = input("Enter path to food image: ")
    analyze_image(image_path)

if __name__ == "__main__":
    main()