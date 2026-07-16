from flask import Flask, request, jsonify
from backend.services.orders import create_order

app = Flask(__name__)

@app.route("/orders", methods=["POST"])
def create_order_view():
    payload = request.get_json() or {}
    order = create_order(payload)
    return jsonify(order), 201

@app.route("/health")
def health():
    return {"status": "ok"}
