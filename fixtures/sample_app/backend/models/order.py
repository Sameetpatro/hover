class OrderRepository:
    def save(self, payload: dict) -> dict:
        return {"id": "ord_1", "items": payload.get("items", []), "status": "created"}
