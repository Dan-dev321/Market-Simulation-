import itertools
import math
MAX_STEP = 0.05     # The most a price can change per tick
BUFFER = 0.5       # The stock that can remain unsold and not result in a price change
FORECAST_WINDOW = 5   # ticks in the moving average
HEADROOM = 0.1        # aim to make slightly more than we expect to sell
HOLDING_RATE = 0.01   # fee per unit of unsold output per tick, as a fraction of production_cost
RESERVE_TICKS = 1   # a firm keeps enough to run at full output for this many ticks
MARKUP = 1.3           # Starting markup over cost
FLOOR_MARKUP = 1.01    # Prices never fall below cost * this
RESERVED_STOCK = 10 # capacity/reserved_stock means how much the firm it trying to keep in capital 
TICKS = 500
SNAPSHOTS = (0, 100, 200, 300, 400, 500)

def cheapest_price(firms, product):
    sellers = [f for f in firms if f.product_sold == product]
    in_stock = [f for f in sellers if f.output_inventory > 0]
    return min(f.price for f in (in_stock or sellers))
 
 
class Consumer:
    def __init__(self, capital):
        self.capital = capital
 
    def purchase(self, firm):
        affordable = self.capital * firm.market_share // firm.price
        units = min(firm.output_inventory, affordable)
        firm.units_wanted = affordable 
        firm.sales_history.append(units)
        firm.output_inventory -= units
        firm.capital += firm.price * units
        self.capital = round(self.capital - firm.price * units, 2)

"""
=============================================================================
                  AGENT-BASED MARKET SIMULATION ROADMAP
=============================================================================
Legend:  [x] done   [0] partly done   [ ] not started
Size:    (S) one short sitting   (M) one session   (L) too big: split first
 
WORKING RULES
  1. One step at a time. The sim must run cleanly before starting the next.
  2. Each step changes ONE mechanism (never pricing + demand + structure).
  3. Any step sized (L), or that grows past (M) mid-way, gets split HERE
     before more code is written.
  4. After a behaviour-changing step, compare the run against the previous
     one (A2/A3 make this possible). Refactor-only steps must match exactly.
 
PROGRESS: 20/57 steps done  (per-phase counts in each header)
 
SUGGESTED ORDER:  A -> B -> C1-C3 -> D1-D3 -> F4-F6 -> G -> rest
DEPENDENCIES:     D4 needs C1 | D5 needs D4 | G5 needs A2 | G6 needs F4
                  G9 needs C5 | E3 needs its own registry rebuild
 
KNOWN ISSUES
  - Consumer-facing prices run away (e.g. houses end near EUR 370k against a
    EUR 30k production cost). Likely cause: demand ignores price, so a sold-out
    tertiary only ever raises price. Phase B improves the signal; the real
    fix is Phase D.
  - Tertiary sell-out raise is a flat SELLOUT_PRESSURE guess (see Phase B).
 
-----------------------------------------------------------------------------
COMPLETED (archive)
-----------------------------------------------------------------------------
[x] Three-tier chain: Primary -> Secondary -> Tertiary -> Consumer.
[x] Closed money loop: production cost paid to consumer as wages; holding
    fees and dividends flow back to the consumer.
[x] Consumer budget split across tertiary firms by market_share.
[x] Initial prices = (production cost + cheapest inputs) * MARKUP.
[x] Price cut on unsold stock; price rise on stock-out (primary/secondary).
[x] Price floors from live input costs, recalculated every tick, using
    in-stock suppliers only.
[x] Synchronous price updates (no list-order bias); 2dp rounding everywhere.
[x] Cheapest-first buying with rollover to next supplier (single pass over a
    sorted list, so no stalls on capacity limits).
[x] Input purchases sized to production targets (bottleneck-aware).
[x] 5-tick moving-average forecast (tertiary); secondary follows downstream
    demand.
[x] Holding costs on unsold output.
[x] Dividends: capital above a reserve is paid out to the consumer.
[x] Capacity balance audit across tiers (done by hand).
[x] Single Firm class; fixed globals in compete() and scrambled constructor
    arguments.
 
-----------------------------------------------------------------------------
PHASE A: OBSERVE & PROTECT (do first)  [4/4]
-----------------------------------------------------------------------------
[x] A1 (S) Conservation check: assert consumer + sum(firm capital) equals the
           starting total each tick (allow ~0.01 rounding). A failure means a
           money leak to track down.
[x] A2 (S) Time-series log: each tick record price, output_inventory, capital
           and units sold per firm, plus consumer capital. In memory only.
[x] A3 (S) End-of-run summary table: prices/stock/capital at ticks
           0, 25, 50, 75, 100.
[x] A4 (S) 500-tick run: note whether prices and stock settle or drift.
 
-----------------------------------------------------------------------------
PHASE B: FINISH TERTIARY PRICING  [0/3]
-----------------------------------------------------------------------------
[x] B1 (S) Consumer.purchase records units wanted vs units bought on the firm.
[x] B2 (S) next_price uses that unmet demand for consumer-facing firms.
[x] B2b (S) Zero downstream demand for a non-consumer-facing firm
            holds price (no raise)
[x] B3 (S) Delete SELLOUT_PRESSURE once B2 works.
 
-----------------------------------------------------------------------------
PHASE C: HOUSEHOLDS  [0/6]
-----------------------------------------------------------------------------
[ ] C1 (S) Propensity to consume: spend only a fraction of capital per tick.
[ ] C2 (S) Household class replaces Consumer (still exactly one household).
           Refactor only: output must match the previous run.
[ ] C3 (S) Second household with different capital and market shares;
           purchases loop over households.
[ ] C4 (S) DECISION, no code: where does the non-wage part of production cost
           go (owners? a second account?). Write the answer here.
[ ] C5 (S) Implement C4 with a labour_share per firm.
[ ] C6 (M) Wage tiers: households receive different shares of wages.
 
-----------------------------------------------------------------------------
PHASE D: ENDOGENOUS CONSUMER DEMAND  [0/6]
-----------------------------------------------------------------------------
[ ] D1 (S) Cobb-Douglas using 0.1/0.6/0.3 as exponents. Must reproduce the
           current purchases exactly (regression check).
[ ] D2 (S) CES with an elasticity parameter; one setting recovers D1.
[ ] D3 (S) Necessity vs luxury: per-good income elasticity.
[ ] D4 (S) Savings: unspent capital carries forward (needs C1).
[ ] D5 (M) Durable goods: buy a house over several ticks via part-payments
           (needs D4).
[ ] D6 (L) Credit. Not yet specified: split into steps before starting.
 
-----------------------------------------------------------------------------
PHASE E: ENTRY, EXIT & FAILURE  [0/6]
-----------------------------------------------------------------------------
NOTE: capital can never go below zero today (fees are capped, buying and
production are limited by cash), so a "capital < 0" test would never fire.
[ ] E1 (S) DECISION: define insolvency (e.g. cannot afford one batch for N
           ticks in a row) and add the counter to Firm.
[ ] E2 (S) is_insolvent() check, logged only. No removal yet.
[ ] E3 (S) Removal: drop the firm from tier lists and all_firms (rebuild the
           registry); leftover capital and stock go to households.
[ ] E4 (S) Rolling profit margin per firm.
[ ] E5 (M) Entrant spawning: clone a template into sectors with high margins
           for K ticks.
[ ] E6 (L) Idle firms shut down or pivot. Split before starting.
 
-----------------------------------------------------------------------------
PHASE F: STRUCTURE & CONFIG  [2/8]
-----------------------------------------------------------------------------
[x] F1     Base class extracted (single Firm class).
[x] F2     Flat all_firms list built once, not rebuilt each tick.
[ ] F3 (S) DECISION: stay with one Firm class, or add thin Primary/Secondary/
           Tertiary subclasses? Only needed if tier mechanics diverge
           (likely after D or E).
[ ] F4 (S) build_world() returns consumer and tiers (no module-level setup).
[ ] F5 (S) Split tick() into named phases: demand, buy, produce,
           clear_market, reprice.
[ ] F6 (S) Simulation class holding state and calling those phases.
[ ] F7 (S) Starting parameters in one dict in code.
[ ] F8 (S) Load that dict from JSON.
 
-----------------------------------------------------------------------------
PHASE G: ANALYTICS & EXPERIMENTS  [0/9]
-----------------------------------------------------------------------------
[ ] G1 (S) Price index (CPI), weighted by market_share.
[ ] G2 (S) Nominal GDP = consumer spending per tick.
[ ] G3 (S) Capacity utilisation = output / capacity.
[ ] G4 (S) Sector profit margins (also feeds E4).
[ ] G5 (M) matplotlib plots of G1-G4 (needs A2).
[ ] G6 (S) Shock hook: apply a change at tick t (needs F4).
[ ] G7 (S) Shock: halve primary output.
[ ] G8 (S) Shock: +50% production costs.
[ ] G9 (S) Shock: cut household income (needs C5).
=============================================================================
"""

class Firm:
    def __init__(self, name, product_sold, capital, capacity, production_cost, recipe=None, input_capacity=None, market_share=None):
        self.name = name
        self.product_sold = product_sold
        self.capital = capital
        self.capacity = capacity                      # max output held
        self.production_cost = production_cost
        self.recipe = recipe or {}
        self.input_capacity = input_capacity or {p: capacity * n for p, n in self.recipe.items()}
        self.market_share = market_share
 
        self.inputs = {p: 0 for p in self.recipe}     # input inventory
        self.units_demanded = {p: 0 for p in self.recipe}
        self.output_inventory = 0
        self.stock_before_sales = 0
        self.sales_history = []
        self.units_wanted = 0                         # B1: what the consumer's budget would have bought
        self.price = 0.0

    # ---- pricing -------------------------------------------------------
 
    def input_cost(self, firms):
        return sum(cheapest_price(firms, p) * n for p, n in self.recipe.items())
 
    def unit_cost(self, firms):
        return self.production_cost + self.input_cost(firms)
 
    def set_initial_price(self, firms):
        self.price = round(self.unit_cost(firms) * MARKUP, 2)
 
    def price_floor(self, firms):
        return round(self.unit_cost(firms) * FLOOR_MARKUP, 2)
 
    def downstream_demand(self, firms):
        return sum(f.units_demanded.get(self.product_sold, 0) for f in firms)
 
    def next_price(self, firms):
        if self.output_inventory == 0:                # sold out: raise price by unmet demand
            if self.market_share is not None:         # consumer-facing: measured at the till
                total, met = self.units_wanted, self.sales_history[-1]
            else:                                     # upstream: measured from firm orders
                total, met = self.downstream_demand(firms), self.stock_before_sales
            pressure = min(max(total - met, 0) / total, 1) if total else 0   # B2b: no demand, no raise
            new_price = self.price * (1 + MAX_STEP * pressure)
        else:                                         # unsold stock: cut price
            unsold = self.output_inventory / self.capacity
            excess = max(unsold - BUFFER, 0) / (1 - BUFFER)
            new_price = self.price * (1 - MAX_STEP * excess)
        return max(round(new_price, 2), self.price_floor(firms))
 
    # ---- demand --------------------------------------------------------
 
    def forecast(self):
        if self.sales_history:
            recent = self.sales_history[-FORECAST_WINDOW:]
            expected = sum(recent) / len(recent)
        else:                                         # first tick: nothing to average yet
            expected = round((self.capacity - self.output_inventory) * 0.1)
        return max(math.ceil(expected * (1 + HEADROOM)), 1)
 
    def demand(self, firms):
        if self.market_share is not None:
            wanted = self.forecast()
        else:
            wanted = self.downstream_demand(firms)
 
        room = self.capacity - self.output_inventory
        target = max(min(wanted - self.output_inventory, room), 0)
 
        for p, n in self.recipe.items():
            need = target * n - self.inputs[p]
            space = self.input_capacity[p] - self.inputs[p]
            self.units_demanded[p] = max(min(need, space), 0)
 
    # ---- trading -------------------------------------------------------
 
    def buy(self, seller, product, units):
        # Hold back some capital per input unit so we can still afford to produce

        "AMOUNT TO PRODUCE 1 UNIT"
        reserve = self.production_cost + sum({self.recipe[k] * cheapest_price(all_firms, k) for k in self.recipe.keys()})
        
        "I WANT THE AMOUNT THAT THE FIRM CAN AFFORD TO MAKE GIVEN THE COST"
        affordable = self.capital // reserve
        room = self.input_capacity[product] - self.inputs[product]
        units = int(min(units, affordable, room, seller.output_inventory))
 
        cost = units * seller.price
        self.capital -= cost
        seller.capital += cost
        seller.output_inventory -= units
        self.inputs[product] += units
        return units
 
    def buy_inputs(self, firms):
        for product, units in self.units_demanded.items():
            sellers = sorted((f for f in firms if f.product_sold == product), key=lambda f: f.price)
            for seller in sellers:
                if units <= 0:
                    break
                units -= self.buy(seller, product, units)
 
    def produce(self, consumer):
        batches = int(min(
            self.capital // self.production_cost,
            self.capacity - self.output_inventory,
            *(self.inputs[p] // n for p, n in self.recipe.items()),
        ))
        cost = batches * self.production_cost
        self.output_inventory += batches
        self.capital -= cost
        consumer.capital += cost                      # production spending is wages to the consumer
        self.stock_before_sales = self.output_inventory
        for p, n in self.recipe.items():
            self.inputs[p] -= batches * n
 
    # ---- end-of-tick money flows --------------------------------------
 
    def charge_holding(self, consumer):
        fee = round(self.output_inventory * self.production_cost * HOLDING_RATE, 2)
        fee = min(fee, self.capital)                  # can't pay more than it has
        self.capital -= fee
        consumer.capital += fee
 
    def pay_dividend(self, consumer):
        reserve = RESERVE_TICKS * self.capacity * self.production_cost
        dividend = round(max(self.capital - reserve, 0), 2)
        self.capital = round(self.capital - dividend, 2)
        consumer.capital = round(consumer.capital + dividend, 2)
 
    def show_status(self):
        print(f"{self.name} has €{self.capital:,.2f} and {self.output_inventory} in stock "
              f"(price €{self.price:,.2f})")


"""Defining starting Conditions for firms and consumers"""


consumer = Consumer(1_000_000)
 
#                 name              product    capital  capacity cost
primary = [
    Firm("Wood Cutters",   "timber",   100_000,   50,   25),
    Firm("CopperWorks",    "copper",   250_000, 1000,  150),
    Firm("StoneCore",      "concrete", 100_000,  500,   20),
    Firm("TmberFactory",   "timber",   200_000, 1000,   26),
]
 
secondary = [
    Firm("North Carpenter", "furniture parts", 100_000,  100, 100, recipe={"timber": 1}),
    Firm("Build-it",        "blocks",           75_000,  500,  30, recipe={"concrete": 1}),
    Firm("Bobs Builds",     "blocks",           50_000,  250,  25, recipe={"concrete": 1}),
    Firm("Processors Inc",  "processors",    1_000_000, 1000,  80, recipe={"copper": 1}),
]
 
tertiary = [
    Firm("IFEA", "furniture", 1_000_000, 2000, 25, recipe={"furniture parts": 3}, input_capacity={"furniture parts": 3500}, market_share=0.1),
    Firm("Houses.Co", "houses", 350_000, 20, 30_000, recipe={"timber": 100, "blocks": 400}, input_capacity={"timber": 1000, "blocks": 2500}, market_share=0.6),
    Firm("PCs", "computers", 2_500_000, 3000, 500, recipe={"processors": 2}, input_capacity={"processors": 6000}, market_share=0.3),
]
 
tiers = [primary, secondary, tertiary]
all_firms = list(itertools.chain(*tiers))
 
# Prices are set tier by tier so each firm can see its suppliers' prices
for firm in all_firms:
    firm.set_initial_price(all_firms)
 
# ---- conservation check (A1) ---------------------------------------------

def total_money():
    return consumer.capital + sum(f.capital for f in all_firms)

START_TOTAL = total_money()          # snapshot before the first tick

def check_conservation(t):
    drift = total_money() - START_TOTAL
    assert abs(drift) < 0.01, f"Money leak at tick {t}: drift of {drift:,.4f}"
    return drift

# ---- time-series log (A2) ------------------------------------------------

history = []     # one entry per tick; history[0] is the starting state

def record(t):
    history.append({
        "tick": t,
        "consumer_capital": consumer.capital,
        "firms": {
            f.name: {
                "price": f.price,
                "stock": f.output_inventory,
                "capital": round(f.capital, 2),
                "sold": f.stock_before_sales - f.output_inventory,
            }
            for f in all_firms
        },
    })

# ---- summary table (A3) --------------------------------------------------

def print_summary(ticks=(0, 25, 50, 75, 100)):
    for metric in ("price", "stock", "capital", "sold"):
        print(f"\n{metric.upper()}")
        print(f"{'':<16}" + "".join(f"{'t=' + str(t):>14}" for t in ticks))
        for f in all_firms:
            row = "".join(f"{history[t]['firms'][f.name][metric]:>14,.2f}" for t in ticks)
            print(f"{f.name:<16}{row}")
    row = "".join(f"{history[t]['consumer_capital']:>14,.2f}" for t in ticks)
    print(f"\n{'Consumer':<16}{row}")
 
# ---- simulation ---------------------------------------------------------
 
def tick():
    for firm in primary:
        firm.produce(consumer)
 
    for tier in (tertiary, secondary):                      # demand flows from consumers back up
        for firm in tier:
            firm.demand(all_firms)
 
    for tier in (secondary, tertiary):
        for firm in tier:
            firm.buy_inputs(all_firms)
            firm.produce(consumer)
    for firm in tertiary:
        consumer.purchase(firm)
 
    for firm in all_firms:
        firm.charge_holding(consumer)
    for firm in all_firms:
        firm.pay_dividend(consumer)
 
    new_prices = [firm.next_price(all_firms) for firm in all_firms]
    for firm, price in zip(all_firms, new_prices):
        firm.price = price
 
 
if __name__ == "__main__":
    max_drift = 0
    record(0)
    for t in range(1, TICKS + 1):
        tick()
        max_drift = max(max_drift, abs(check_conservation(t)))
        record(t)
    for firm in all_firms:
        firm.show_status()
    print(f"Consumer has €{consumer.capital:,.2f}")
    print(f"Max money drift over run: {max_drift:.6f}")
    print_summary(SNAPSHOTS)

    print("\nB1 check (last tick):")
    for f in tertiary:
        print(f"{f.name:<12} wanted {f.units_wanted:>8,.0f}  bought {f.sales_history[-1]:>8,.0f}")