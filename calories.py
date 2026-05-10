# Calorie Database
# Common foods and their calories per 100g

FOOD_DATABASE = {
    # Grains & Carbs
    "rice": 130,
    "bread": 265,
    "pasta": 131,
    "naan": 310,
    "chapati": 297,

    # Proteins
    "chicken": 165,
    "beef": 250,
    "fish": 136,
    "egg": 155,
    "lentils": 116,

    # Vegetables
    "salad": 15,
    "tomato": 18,
    "potato": 77,
    "onion": 40,
    "spinach": 23,
    "peas": 81,
    "carrots": 41,
    "broccoli": 34,
    "green beans": 31,
    "mushrooms": 22,
    "butternut squash": 45,

    # Dairy
    "milk": 42,
    "cheese": 402,
    "yogurt": 59,

    # Fruits
    "banana": 89,
    "apple": 52,
    "mango": 60,

    # Fast food
    "burger": 295,
    "pizza": 266,
    "fries": 312,

    # Sweets & Desserts
    "ice cream": 207,
    "waffle cone": 377,
    "chocolate": 546,
    "cake": 257,
    "cookie": 502,

    # Drinks
    "milk": 42,
    "juice": 45,
    "soda": 41,

    # Snacks
    "chips": 536,
    "popcorn": 375,
    "nuts": 607,
}

def get_calories(food_name, grams=100):
    """
    Returns calories for a food item with fuzzy matching
    """
    food = food_name.lower().strip()
    
    # Exact match first
    if food in FOOD_DATABASE:
        calories = (FOOD_DATABASE[food] * grams) / 100
        return calories
    
    # Fuzzy match — check if any database key is IN the food name
    for key in FOOD_DATABASE:
        if key in food:
            calories = (FOOD_DATABASE[key] * grams) / 100
            print(f"  (matched '{food_name}' → '{key}')")
            return calories
    
    print(f"  '{food_name}' not found in database")
    return 0

def list_all_foods():
    """
    Prints all available foods
    """
    print("\n Available foods in database:")
    for food in FOOD_DATABASE:
        print(f"  {food}: {FOOD_DATABASE[food]} cal/100g")

def search_by_calories(min_cal, max_cal):
    """
    Find foods within a calorie range per 100g
    """
    print(f"\n🔍 Foods between {min_cal}-{max_cal} cal per 100g:")
    found = []
    for food, calories in FOOD_DATABASE.items():
        if min_cal <= calories <= max_cal:
            found.append(food)
            print(f"  {food}: {calories} cal")
    
    if not found:
        print("  No foods found in that range!")
    
    return found