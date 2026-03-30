def _pick_host(...):
    # Existing code
    host = ...

    # Update line 887 to safely extract IP addresses from hosts
    ip_address = h.get("ip") if isinstance(h, dict) else (h[0] if len(h) > 0 else "?")
    
    # Continue with existing logic
    ...

# Helper functions for consistent host extraction

def extract_host_ip(h):
    return h.get("ip") if isinstance(h, dict) else (h[0] if len(h) > 0 else "?")

# Update all occurrences where host data handling is implemented throughout the file to use extract_host_ip
