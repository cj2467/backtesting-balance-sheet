# Feedback 
Thank you for the strong submission. The ALM/NIR backtesting scenario feels realistic and clearly draws on hands-on banking experience. The best design choice is the cascading structure: actualizing one product affects funding, balance sheet balancing, NIR, and variance attribution downstream.

As you build this out in Phase 2, focus on these areas:

1. Tighten the scenario into one specific engagement. Pick the bank profile, forecast date, backtest period, product list, and actualization sequence. Remove exploratory notes like “Is this how FTP works?” or “could even be stock-level data,” and make firm design choices.

2. Simplify the prompt. Make it sound like a request from an ALM or FP&A lead, not instructions to an AI. For example: “Backtest last year’s NIR forecast using the attached actuals, maintain a balanced average balance sheet after each actualization step, and prepare product-level variance attribution.”

3. Define the balancing/funding mechanics clearly. Decide how excess asset balances are funded, how margin overfunding works, whether there is an FTP/liability stack, and how HTM/AFS securities, accruals, day-count conventions, and daily-to-monthly aggregation should be handled. These rules will drive the task’s sequential complexity.

4. Make the Phase 2 rubric numerically checkable. Build the model yourself and include anchor checks: starting forecast tie-out, product-level actual balances/yields/NIR, balance sheet equality after each step, reconciliation to source-of-truth actuals, total NIR error, and variance attribution by product.

This is a strong foundation for a realistic corporate finance modeling task. With clearer scope and firm mechanics, it should become a very effective Phase 2 build.


# Scenario

Backtesting is used to test a Net Interest Revenue at a Bank to ensure that the model correctly interacts with the actualization of each piece, the error for each product is not too high, and under a real interest rate scenario, the banks assets would still be valued enough to cover the liabilities. Following the guidance from the federal reserve (SR 10-1 and SR 15-18), most banks of a certain size are required to follow backtesting for their Net Interest Revenue Forecast. They also need to layer in different interest rate shocks, which I will not cover in this proposal. For the sake of this task, much of the data is described as exported from data tables into clean excel or csv descriptions for the models ability to generate artifacts

A Net Interest Revenue Forecast ties together the Balance Sheet and the yield the Balance Sheet items earn. For the execution of Backtesting, the project starts with the Net Interest Revenue Forecast and many, often disparate, sources of granular actuals required to actualize the Balance Sheet balances and yields product by product. Using a stepwise approach allows the bank to see which products are contributing the most error and how that permeates through the rest of the sheet as the Assets need to be funded by Liabilities.

# Prompt

Build a backtesting project compliant with the FRB SR 10-1 from the provided simple Net Interest Revenue forecast on a consolidated level for each product with matching Balance Sheet and annualized yield forecasts. Please roll back the current forecasting methodology to a year ago, then layer in the actuals for each product to build out a step by step forecast of each balance or rate being actualized. This forecast should be dynamic, specifically with fluctuating forecasts for balances and yields while balancing average Assets and Liabilities at each step of adding assets. Start with forecasts that come from separate teams then Liabilities and finally actualize the products inherent to the model when you do the actualization steps.

# Context files
1. Starting Balance Sheet and Product specific yield forecasts that combine to form a Net Interest Revenue forecast. This is a three sheet excel document that is normalized to Actual / Actual annualized yields. It represents a gross simplification of all the intertwined calculations that go into a full Net Interest Revenue forecast. The Products include, on the consolidated Asset the Liability side:
Export of a data table for the total Deposit month by month Average Balance and yield paid to customers, split by total interest bearing and non interest bearing deposits.
A saved teams message with the monthly splits for Checking and Savings deposit rates and balances for each month end of the year in markdown.
A csv with Securitized Debt issuance and redemption dates with amounts and coupons.
Senior and subordinated notes issuance documents for each share class with the amount, valuation, interest paid, and tranche for the notes active during the target year.
Table with business day data for Margin balance and earned yield.
Nuance here is that margin needs to be funded above 100% so actualization will have ripple effects through the whole funding stack. Is this how FTP works? Product level profitability calculation with funding in mind?
Could even be stock level data that needs to be summed up for each day
Trade data for bond level asset holdings, down to the CUSIP level for each individual trade. This will need to be noted to be in different categories as Held to Maturity or Available for Sale. Carrying Value, par value, cost basis, and either loan level or total allowance for loss will need to be included.
Cash due from banks actuals with Daily Yield and interest received. (Same as Cash and Cash Equivalents)
Will have to calculate back balance.
Short Term Investments with balance, yield, maturity, cusip with type of investment, and purchase date.
Accounting table of actuals balance for Other Borrowings with yield and amount paid out.
A schedule of interest payable and other accrued expenses and liabilities.
Fed Funds Purchased and maturities for each lot.
A schedule of non Interest earning items in a database.
*Much of this is simplified to be able to fit in the context of a three sheet Net Interest Revenue forecast. Can add more unnecessary columns as needed to challenge the model.

# Verificability

The Balance Sheet forecast balances (Assets = Liabilities + Equity) at the start, then also at each step of the actualization.
Review each line item that has been actualized for balances and yield, then compare them and the calculated revenue with the line in the accounting source of truth.
Understand the net effect of each actualization on Net Interest Revenue (NIR) from a percent and absolute amount perspective.
Be able to attribute the difference in NIR at each step to specific accounts changed in each step and deliver a narrative of what makes sense and what errors are still inherent to the model.

I expect the AI to fair in two major ways, one by reverting or incorrectly actualizing the line items at specific steps on the way, and two by not actualizing the other side of the balance sheet.

Second failure points will be incorrect Net Interest Revenue calculated through improper yields, balances, or the multiplication of the two.

The third failure point is around improper analysis of the results and understanding where error in the forecasting process is coming from.