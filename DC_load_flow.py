import numpy as np

def dc_power_flow_balanced(buses, lines, ref_bus=0):
    """
    Berechnet den DC-Lastfluss für ein Netz, bei dem alle Leistungen (auch die 
    des Referenzknotens) im Vorfeld fest vorgegeben und ausbalanciert sind.
    """
    n_buses = len(buses)
    
    # 1. Leistungsbilanz prüfen (Summe aller P muss nahe 0 sein)
    total_power = sum(buses)
    if abs(total_power) > 1e-6:
        print(f"⚠️ WARNUNG: Dein Netz ist nicht ausbalanciert! Die Summe der Leistungen ist {total_power:.4f} p.u.")
        print("Das physikalische Modell geht davon aus, dass Erzeugung und Last gleich sind.")
        print("-" * 50)
    
    # 2. B'-Matrix mit Nullen initialisieren und befüllen
    B_prime = np.zeros((n_buses, n_buses))
    
    for from_node, to_node, x in lines:
        b = 1.0 / x
        B_prime[from_node, from_node] += b
        B_prime[to_node, to_node] += b
        B_prime[from_node, to_node] -= b
        B_prime[to_node, from_node] -= b
        
    # 3. Referenzknoten (Winkel = 0) mathematisch eliminieren, um Matrix lösbar zu machen
    active_buses = [i for i in range(n_buses) if i != ref_bus]
    
    B_red = B_prime[np.ix_(active_buses, active_buses)]
    P_red = np.array([buses[i] for i in active_buses])
    
    # 4. Winkel berechnen und Referenzwinkel (0.0) wieder einfügen
    theta_red = np.linalg.solve(B_red, P_red)
    
    theta = np.zeros(n_buses)
    for idx, bus_id in enumerate(active_buses):
        theta[bus_id] = theta_red[idx]
        
    # 5. Leistungsflüsse auf den Leitungen berechnen
    line_flows = []
    for from_node, to_node, x in lines:
        flow = (theta[from_node] - theta[to_node]) / x
        line_flows.append({
            'von': from_node,
            'nach': to_node,
            'fluss': flow
        })
        
    return theta, line_flows


# ==========================================
# BEISPIEL: Komplett ausbalanciertes 3-Knoten-Netz
# ==========================================
print("--- TEST: Ausbalanciertes Netz ---")

# Vorgabe: Knoten 0 erzeugt 0.5, Knoten 1 verbraucht 1.0, Knoten 2 erzeugt 0.5
# Summe = 0.5 - 1.0 + 0.5 = 0.0 (Das Netz passt physikalisch perfekt!)
buses_input = [0.5, -1.0, 0.5]

lines_input = [
    (0, 1, 0.1),  
    (0, 2, 0.2),  
    (2, 1, 0.2)   
]

# Berechnung starten
winkel, fluesse = dc_power_flow_balanced(buses_input, lines_input, ref_bus=0)

# Ergebnisse anzeigen
print("\nPhasenwinkel (rad):", np.round(winkel, 4))
print("\nLeistungsflüsse:")
for f in fluesse:
    print(f"  Leitung {f['von']} -> {f['nach']}: {f['fluss']:.4f} p.u.")