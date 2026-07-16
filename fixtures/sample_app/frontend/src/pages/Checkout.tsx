export function Checkout() {
  async function submit() {
    await fetch("/orders", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items: ["sku-1"] }),
    });
  }
  return <button onClick={submit}>Place order</button>;
}
