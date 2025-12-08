import json
from flask import Flask, render_template, request, jsonify
import pandas as pd

app = Flask(__name__)

with open("files/regions.json") as f:
    regions = json.load(f)


region_slug_map = {region["href"]: region for region in regions}

df = pd.read_csv("files/data.csv")

soil_stats_df = pd.read_csv("files/soil_stats.csv")
soil_stats_map = {
    row["RegionName"]: {
        "soil_1": row["1st_top_soil_type"],
        "soil_2": row["2st_top_soil_type"],
        "n_range": row["median_nitrogen_levels"],
        "p_range": row["median_phosphorus_levels"],
        "ph_range": row["median_ph_levels"]
    }
    for _, row in soil_stats_df.iterrows()
}

@app.route("/favicon.ico")
def favicon():
    #To ingner the favicon.ico request from the browser
    return "", 204

@app.route("/")
def index():
    return render_template("index.html", regions=regions)

def format_coords(poly):
    return ','.join(f'{x},{y}' for x, y in poly)

app.jinja_env.filters["format_coords"] = format_coords

def get_bounds(polygons):
    all_points = [pt for poly in polygons for pt in poly]
    min_x = min(x for x, _ in all_points)
    max_x = max(x for x, _ in all_points)
    min_y = min(y for _, y in all_points)
    max_y = max(y for _, y in all_points)
    return min_x, max_x, min_y, max_y

@app.route("/<path:slug>")
def catch_all(slug):
    if slug.startswith("robots") and slug.endswith(".txt"):
        return "", 204
    return "", 404  

@app.errorhandler(404)
def page_not_found(e):
    return "", 204  

@app.route("/<slug>")
def region_page(slug):
    region = region_slug_map.get(slug)
    if not region:
        return "", 204  
    min_x, max_x, min_y, max_y = get_bounds(region["normalized_polygons"])

    region_name = region["RegionName"]
    region_area = round(df[df["Region"] == region_name]["region_area"].iloc[0] * 0.0001, 2) # converting m^2 to ha, rounding to 2nd decimal

    soil_stats = soil_stats_map.get(region_name, {})

    return render_template(
        "region.html",
        region=region,
        min_x=min_x,
        max_x=max_x,
        min_y=min_y,
        max_y=max_y,
        soil_stats=soil_stats,
        region_area=region_area
    )

with open("models/predictions_2020.json") as f:
    predictions = json.load(f)


@app.route("/api/yield")
def get_yield():
    slug = request.args.get("region")
    year = int(request.args.get("year"))

    region_obj = region_slug_map.get(slug)
    if not region_obj:
        return jsonify({"error": "Invalid region"}), 400

    region_name = region_obj["RegionName"]
    filtered = df[(df["Region"] == region_name) & (df["Year"] == year)]

    predicted_yield = predictions.get(region_name)

    if filtered.empty:
        return jsonify({"yield": None,
                        "predicted_yield" : round(predicted_yield, 1)})

    value = filtered["Production"].iloc[0]
    if pd.isna(value):
        return jsonify({"yield": None,
                        "predicted_yield" : round(predicted_yield, 1)})


    return jsonify({"yield": round(float(value), 1),
                    "predicted_yield" : round(predicted_yield, 1)})


def get_region_years(slug):
    region_obj = region_slug_map.get(slug)
    if not region_obj:
        return []

    region_name = region_obj["RegionName"]

    years_df = df[df["Region"] == region_name]["Year"].unique()
    veg_years_df = ndvi_df[ndvi_df["Region"] == region_name]["Year"].dropna().unique()

    years = sorted(set(int(y) for y in years_df) | set(int(y) for y in veg_years_df))
    return years

@app.route("/api/years")
def api_years():
    slug = request.args.get("region")
    years = get_region_years(slug)
    return jsonify(years)


@app.route("/api/data")
def get_data():
    slug = request.args.get("region")  #slug 
    year = int(request.args.get("year"))
    granularity = request.args.get("granularity")
    variable = request.args.get("variable")

    region_obj = region_slug_map.get(slug)
    if not region_obj:
        return jsonify({"error": "Invalid region"}), 400

    region_name = region_obj["RegionName"]  #original name 
    
    filtered = df[(df["Region"] == region_name) & (df["Year"] == year)]

    if granularity == "monthly":
        grouped = filtered.groupby("Month")[variable].mean()
    elif granularity == "seasonal":
        grouped = filtered.groupby("Season")[variable].mean()
    else:  # daily
        grouped = filtered.groupby("Date")[variable].mean()

    return jsonify(grouped.to_dict())

ndvi_df = pd.read_csv("files/ndvi_data.csv")

@app.route("/api/seasons")
def get_seasons():
    slug = request.args.get("region")
    region_obj = region_slug_map.get(slug)
    if not region_obj:
        return jsonify([])

    region_name = region_obj["RegionName"]
    seasons = ndvi_df[ndvi_df["Region"] == region_name]["Season"].dropna().unique().tolist()
    return jsonify(sorted(seasons))

@app.route("/api/vegetation")
def get_vegetation_data():
    slug = request.args.get("region")
    year_str = request.args.get("year")
    season = request.args.get("season")

    if not slug or not year_str or not season:
        return jsonify({"error": "Missing required parameters"}), 400

    try:
        year = int(year_str)
    except ValueError:
        return jsonify({"error": "Invalid year format"}), 400

    region_obj = region_slug_map.get(slug)
    if not region_obj:
        return jsonify({"error": "Invalid region"}), 400

    region_name = region_obj["RegionName"]

    filtered = ndvi_df[
        (ndvi_df["Region"] == region_name) &
        (ndvi_df["Year"] == year) &
        (ndvi_df["Season"] == season)
    ]

    summary = { # Omitting the other 2 categories
        "Sparse": filtered["Sparse Veg"].sum(),
        "Moderate": filtered["Moderate Veg"].sum(),
        "Dense": filtered["Dense Veg"].sum(),
        "Very Dense": filtered["Very Dense Veg"].sum()
    }

    return jsonify(summary)

if __name__ == "__main__":
    app.run(debug=True)