import streamlit as st
import requests
import pydeck as pdk

API_URL = "http://localhost:8000/score"

st.title("CAPEX Cloud Viewer")

coords = st.text_input("lat,lon")

if coords:

    lat, lon = map(float, coords.split(","))

    res = requests.post(API_URL, json={
        "lat": lat,
        "lon": lon
    }).json()

    st.success(res["score"])

    best = res["location"]

    layers = []

    layers.append(pdk.Layer(
        "ScatterplotLayer",
        data=[{"position": [lon, lat]}],
        get_position="position",
        get_radius=120,
        get_fill_color=[255, 0, 0]
    ))

    layers.append(pdk.Layer(
        "ScatterplotLayer",
        data=[{"position": best}],
        get_position="position",
        get_radius=120,
        get_fill_color=[0, 255, 0]
    ))

    st.pydeck_chart(pdk.Deck(
        layers=layers,
        initial_view_state=pdk.ViewState(
            latitude=lat,
            longitude=lon,
            zoom=11
        ),
        map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"
    ))