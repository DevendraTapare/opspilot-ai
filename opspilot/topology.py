"""Fixed fictional service topology, shared by transport and evidence validation."""

DEPENDENCIES = {
    "checkout-service": ["payment-service", "inventory-service"],
    "payment-service": [],
    "inventory-service": [],
}
