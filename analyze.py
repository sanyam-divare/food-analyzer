# Food Analyzer - AI powered calorie tracker
# Author: Sanyam
# Started: May 2026

import os
import json
from datetime import datetime
from calories import get_calories, list_all_foods

def analyze_image(image_path):
    """
    Takes a food image and returns detected foods
    Later: this will connect to local AI model
    """
    print(f"\nAnalyzing image: {image_path}")
    # TODO: connect to Ollama + LLaVA/Gemma3
    # For now, manually enter foods
    foods = []
    print("(AI not connected yet — enter foods manually)")
    print("Type food name and grams, or 'done' to finish\n")

    while True:
            food = input("Food item (or 'done'): ").strip()
            if food.lower() == "done":
                break
            if food == "":
                print("Please enter a food name!")
                continue
            try:
                grams = float(input(f"Grams of {food}: "))
                foods.append({"name": food, "grams": grams})
            except ValueError:
                print("Please enter a valid number for grams!")

    return foods

def calculate_calories(foods):
    """
    Takes a list of foods and returns total calories
    """
    print("\n📊 Calorie Breakdown:")
    total = 0
    for item in foods:
        cal = get_calories(item["name"], item["grams"])
        print(f"  {item['name']} ({item['grams']}g): {cal:.0f} cal")
        total += cal
    print(f"\n🔥 Total: {total:.0f} calories")
    return total

def save_to_log(foods, calories):
    """
    Saves meal analysis to a local JSON log file
    """
    log_file = "meals_log.json"

    # Load existing log if it exists
    if os.path.exists(log_file):
        with open(log_file, "r") as f:
            log = json.load(f)
    else:
        log = []

    # Add new entry
    entry = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "foods": foods,
        "total_calories": calories
    }
    log.append(entry)

    # Save back to file
    with open(log_file, "w") as f:
        json.dump(log, f, indent=2)

    print(f"\n✅ Meal saved to {log_file}")

def show_history():
    """
    Shows previous meals from log
    """
    log_file = "meals_log.json"
    if not os.path.exists(log_file):
        print("No meal history yet!")
        return

    with open(log_file, "r") as f:
        log = json.load(f)

    print("\n📅 Meal History:")
    for entry in log:
        print(f"\n  {entry['date']}")
        for food in entry['foods']:
            print(f"    - {food['name']}: {food['grams']}g")
        print(f"  🔥 Total: {entry['total_calories']:.0f} cal")

def main():
    print("🍽️  Food Analyzer")
    print("==================")
    print("1. Analyze a meal")
    print("2. Show food database")
    print("3. Show meal history")
    choice = input("\nChoose (1/2/3): ")

    if choice == "1":
        image_path = input("Enter image path (or press Enter to skip): ")
        foods = analyze_image(image_path)
        if foods:
            calories = calculate_calories(foods)
            save_to_log(foods, calories)
    elif choice == "2":
        list_all_foods()
    elif choice == "3":
        show_history()
    else:
        print("Invalid choice!")

if __name__ == "__main__":
    main()