def ajust_order_costs_benefit(pmt_amt, order_amt, benefit, cost) :
    
    diff = order_amt - pmt_amt
    
    if diff > 0 :
        if pmt_amt > cost :
            cost_ajusted = cost
            benefit_ajusted = benefit - diff
        else :
            cost_ajusted = pmt_amt
            benefit_ajusted = 0
    elif diff < 0 :
        cost_ajusted = cost
        benefit_ajusted = benefit - diff
    else :
        benefit_ajusted = benefit
        cost_ajusted = cost
        
    return benefit_ajusted, cost_ajusted, diff

print(ajust_order_costs_benefit(22500, 20000, 10035, 9965))
