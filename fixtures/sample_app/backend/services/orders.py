from backend.models.order import OrderRepository
from workers.notify import enqueue_notification

repo = OrderRepository()

def create_order(payload: dict) -> dict:
    order = repo.save(payload)
    enqueue_notification(order["id"])
    return order
