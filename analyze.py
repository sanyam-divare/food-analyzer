# # Food Analyzer - AI powered calorie tracker
# # Author: Sanyam
# # Started: May 2026

# import os
# import json
# from datetime import datetime
# from calories import get_calories, list_all_foods

# def analyze_image(image_path):
#     """
#     Takes a food image and returns detected foods
#     Later: this will connect to local AI model
#     """
#     print(f"\nAnalyzing image: {image_path}")
#     # TODO: connect to Ollama + LLaVA/Gemma3
#     # For now, manually enter foods
#     foods = []
#     print("(AI not connected yet — enter foods manually)")
#     print("Type food name and grams, or 'done' to finish\n")

#     while True:
#             food = input("Food item (or 'done'): ").strip()
#             if food.lower() == "done":
#                 break
#             if food == "":
#                 print("Please enter a food name!")
#                 continue
#             try:
#                 grams = float(input(f"Grams of {food}: "))
#                 foods.append({"name": food, "grams": grams})
#             except ValueError:
#                 print("Please enter a valid number for grams!")

#     return foods

# def calculate_calories(foods):
#     """
#     Takes a list of foods and returns total calories
#     """
#     print("\n📊 Calorie Breakdown:")
#     total = 0
#     for item in foods:
#         cal = get_calories(item["name"], item["grams"])
#         print(f"  {item['name']} ({item['grams']}g): {cal:.0f} cal")
#         total += cal
#     print(f"\n🔥 Total: {total:.0f} calories")
#     return total

# def save_to_log(foods, calories):
#     """
#     Saves meal analysis to a local JSON log file
#     """
#     log_file = "meals_log.json"

#     # Load existing log if it exists
#     if os.path.exists(log_file):
#         with open(log_file, "r") as f:
#             log = json.load(f)
#     else:
#         log = []

#     # Add new entry
#     entry = {
#         "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
#         "foods": foods,
#         "total_calories": calories
#     }
#     log.append(entry)

#     # Save back to file
#     with open(log_file, "w") as f:
#         json.dump(log, f, indent=2)

#     print(f"\n✅ Meal saved to {log_file}")

# def show_history():
#     """
#     Shows previous meals from log
#     """
#     log_file = "meals_log.json"
#     if not os.path.exists(log_file):
#         print("No meal history yet!")
#         return

#     with open(log_file, "r") as f:
#         log = json.load(f)

#     print("\n📅 Meal History:")
#     for entry in log:
#         print(f"\n  {entry['date']}")
#         for food in entry['foods']:
#             print(f"    - {food['name']}: {food['grams']}g")
#         print(f"  🔥 Total: {entry['total_calories']:.0f} cal")

# def main():
#     print("🍽️  Food Analyzer")
#     print("==================")
#     print("1. Analyze a meal")
#     print("2. Show food database")
#     print("3. Show meal history")
#     choice = input("\nChoose (1/2/3): ")

#     if choice == "1":
#         image_path = input("Enter image path (or press Enter to skip): ")
#         foods = analyze_image(image_path)
#         if foods:
#             calories = calculate_calories(foods)
#             save_to_log(foods, calories)
#     elif choice == "2":
#         list_all_foods()
#     elif choice == "3":
#         show_history()
#     else:
#         print("Invalid choice!")

# if __name__ == "__main__":
#     main()


# Food Analyzer - AI powered calorie tracker
# Author: Sanyam
# Started: May 2026

import os
import json
import requests
import base64
from datetime import datetime
from dotenv import load_dotenv
from calories import get_calories, list_all_foods

# Load API key from .env file
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

def image_to_base64(image_path):
    """
    Converts image file to base64 string for API
    """
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def analyze_image_with_ai(image_path):
    """
    Sends image to Gemini and gets food list back
    """
    print(f"\n🤖 Analyzing image with Gemini AI...")

    # Convert image to base64
    image_data = image_to_base64(image_path)

    # Detect image type
    ext = image_path.lower().split(".")[-1]
    mime_types = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
    }
    mime_type = mime_types.get(ext, "image/jpeg")

    # Build API request
    # url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"

    # payload = {
    #     "contents": [{
    #         "parts": [
    #             {
    #                 "inline_data": {
    #                     "mime_type": mime_type,
    #                     "data": image_data
    #                 }
    #             },
    #             {"text": """Analyze this food image. List each food item you see.
    #                 Be specific with food names e.g. 'raw banana' not just 'banana',
    #                 'cooked white rice' not just 'rice', 'grilled chicken breast' not just 'chicken'.
    #                 Respond ONLY in this exact JSON format, no other text:
    #                 {
    #                     "foods": [
    #                         {"name": "specific food name", "estimated_grams": 100}
    #                     ],
    #                     "meal_description": "brief description"
    #                 }"""
    #             }
    #         ]
    #     }]
    # }
    payload = {
        "contents": [{
            "parts": [
                {
                    "inline_data": {
                        "mime_type": mime_type,
                        "data": image_base64
                    }
                },
                {"text": """You are an expert food analyst and nutritionist.
            Analyse this food plate image carefully.

            RULES:
            1. Identify every distinct food item visible on the plate
            2. Be specific - use the most precise food name possible
            3. For cooking method: use 'raw', 'grilled', 'fried', 'boiled', 
            'steamed', 'baked', 'roasted', 'sauteed'
            4. For leafy greens: identify the specific type if visible 
            (spinach/rocket/cos lettuce/baby spinach/mixed leaves)
            - if truly cannot identify, use 'mixed leafy salad greens'
            5. For sauces/dressings: identify as specifically as possible
            (mayonnaise/tomato sauce/chilli sauce/yoghurt dressing)
            6. Estimate weight in grams based on visual portion size
            7. Confidence: 'high' if clearly visible, 
                        'medium' if partially visible or overlapping,
                        'low' if guessing based on context
            8. Consider ALL cuisines - Australian, Indian, Asian, 
            Mediterranean, Middle Eastern, etc.

            Respond ONLY in this exact JSON format, no other text:
            {
                "foods": [
                    {
                        "name": "specific food name",
                        "cooking_method": "raw|grilled|fried|boiled|steamed|baked|roasted|sauteed|not applicable",
                        "category": "protein|grain|vegetable|fruit|dairy|sauce|condiment|beverage",
                        "estimated_grams": 100,
                        "confidence": "high|medium|low",
                        "visual_notes": "brief note on what you actually see"
                    }
                ],
                "meal_description": "brief description",
                "cuisine_type": "Indian|Australian|Asian|Mediterranean|Western|Mixed|Unknown",
                "plate_coverage": "full|partial|half eaten"
            }"""
                        }
                    ]
                }]
            }



    # Call Gemini API
    response = requests.post(url, json=payload)

    if response.status_code == 200:
        result = response.json()
        text = result["candidates"][0]["content"]["parts"][0]["text"]

        # Clean and parse JSON response
        text = text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        text = text.strip()

        data = json.loads(text)
        print(f"🍽️  {data['meal_description']}")
        return data["foods"]
    else:
        print(f"❌ API Error: {response.status_code}")
        print(response.text)
        return []

def analyze_manually():
    """
    Manual food entry when no image available
    """
    foods = []
    print("\n📝 Enter foods manually:")
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
            foods.append({"name": food, "estimated_grams": grams})
        except ValueError:
            print("Please enter a valid number!")

    return foods

def calculate_calories(foods):
    """
    Calculates calories for detected foods
    """
    print("\n📊 Calorie Breakdown:")
    total = 0
    for item in foods:
        grams = item.get("estimated_grams", 100)
        cal = get_calories(item["name"], grams)
        print(f"  {item['name']} ({grams}g): {cal:.0f} cal")
        total += cal
    print(f"\n🔥 Total: {total:.0f} calories")
    return total

def save_to_log(foods, calories):
    """
    Saves meal to local JSON log
    """
    log_file = "meals_log.json"
    log = []

    if os.path.exists(log_file):
        with open(log_file, "r") as f:
            log = json.load(f)

    entry = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "foods": foods,
        "total_calories": calories
    }
    log.append(entry)

    with open(log_file, "w") as f:
        json.dump(log, f, indent=2)

    print(f"\n✅ Meal saved to log!")

def show_history():
    """
    Shows previous meals
    """
    log_file = "meals_log.json"
    if not os.path.exists(log_file):
        print("No meal history yet!")
        return

    with open(log_file, "r") as f:
        log = json.load(f)

    print("\n📅 Meal History:")
    for entry in log:
        print(f"\n  📅 {entry['date']}")
        for food in entry["foods"]:
            print(f"    - {food['name']}: {food.get('estimated_grams', '?')}g")
        print(f"  🔥 Total: {entry['total_calories']:.0f} cal")

def main():
    print("🍽️  Food Analyzer - AI Edition")
    print("================================")
    print("1. Analyze food image with AI")
    print("2. Enter foods manually")
    print("3. Show food database")
    print("4. Show meal history")

    choice = input("\nChoose (1/2/3/4): ")

    if choice == "1":
        image_path = input("Enter image path: ").strip()
        if os.path.exists(image_path):
            foods = analyze_image_with_ai(image_path)
            if foods:
                calories = calculate_calories(foods)
                save_to_log(foods, calories)
        else:
            print("❌ Image file not found!")

    elif choice == "2":
        foods = analyze_manually()
        if foods:
            calories = calculate_calories(foods)
            save_to_log(foods, calories)

    elif choice == "3":
        list_all_foods()

    elif choice == "4":
        show_history()

    else:
        print("Invalid choice!")

if __name__ == "__main__":
    main()