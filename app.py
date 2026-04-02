@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()

    if not data:
        print("No data received")
        return jsonify({"error": "No data"}), 400

    print("Webhook data received:", data)

    action = data.get("action")
    symbol = data.get("symbol")
    sl = data.get("sl")
    tp = data.get("tp")
    score = float(data.get("score", 0))

    # SNIPER FILTER
    if score < 80:
        print("Skipped trade: low score", score)
        return jsonify({"status": "skipped", "reason": "low score"})

    status, response = place_order(symbol, action, sl, tp)

    print("OANDA status:", status)
    print("OANDA response:", response)

    return jsonify({
        "status": "executed",
        "oanda_status": status,
        "response": response
    }))
