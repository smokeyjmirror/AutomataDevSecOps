import Std

namespace Automata

/-- A service contract for an inter-planetary fulfillment request. -/
structure ServiceContract where
  routeRisk : Nat
  paymentEscrowed : Bool

/-- Maximum route risk tolerated before a contract requires review. -/
def maxRouteRisk : Nat := 3

/-- A contract is approval-eligible only when its route is within tolerance and funds are secured. -/
def isApprovalEligible (c : ServiceContract) : Bool :=
  c.routeRisk < maxRouteRisk && c.paymentEscrowed

/-- If a contract is approved, the route is within the safe limit and funds are escrowed. -/
theorem approval_requires_safe_route_and_funds (c : ServiceContract)
    (h : isApprovalEligible c = true) :
    c.routeRisk < maxRouteRisk ∧ c.paymentEscrowed := by
  simp [isApprovalEligible] at h
  exact h

/-- Example contract with acceptable route risk and payment escrow. -/
example : isApprovalEligible { routeRisk := 2, paymentEscrowed := true } = true := by
  decide

/-- Example contract with an unsafe route despite escrowed funds. -/
example : isApprovalEligible { routeRisk := 4, paymentEscrowed := true } = false := by
  decide

/-- Example contract with a safe route but no escrowed funds. -/
example : isApprovalEligible { routeRisk := 2, paymentEscrowed := false } = false := by
  decide

end Automata
