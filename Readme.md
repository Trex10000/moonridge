# **MoonRidge**

A prototype stock screener for investors who think in years, not minutes.

Fundamentals, financials, insights \- everything you need to find your next conviction. Covering 6,670+ active US stocks across NYSE, NASDAQ, NYSE ARCA, BATS, and AMEX.

---

## **What is MoonRidge?**

MoonRidge is a research tool for long term investors. Search any US stock, explore its financials across a decade of history, compare it against peers and ask natural language questions to Freysa, our AI powered by Claude.

---

## **Features**

### **Search & Explore**

Search by ticker or company name across 6,670+ US stocks. Every stock has a detailed profile page showing company description, sector, industry, exchange, IPO date, and a direct link to the company's website.

![Search Bar](screenshots/searchbar.png)

### **Stock Overview**

Each stock's page opens with the current closing price, daily change, open/high/low, and key valuation metrics: market cap, book value, 52-week range, Return On Assets (ROA), Return On Equity (ROE) etc.

\!\[ticker\](screenshots/ticker.png)

**Historical Closing Price**

Interactive price chart showing adjusted closing price over any range \- 1 month to max history (20+ years for most stocks). Customizable with grid toggle, dark/light background, line and axis color pickers, and x-axis label rotation. Download the chart as an image or PDF or data in CSV format.

\!\[cp chart\](screenshots/cpchart.png)

### **Financials**

Full income statement data going back 10+ years, annual and quarterly. Explore revenue, gross profit, operating income, EBITDA, net income, R\&D, SG\&A, and more.

Every metric row has a chart icon \- click it to open a dedicated chart modal with time range selection (1Y to Max), multi-company comparison (add any ticker), and a Raw/Indexed/Log display toggle.

\!\[financials\](screenshots/financials.png)

#### **Revenue & Margin Waterfall**

Visual breakdown of how revenue flows through costs and expenses to net income. Shows cost of revenue, gross profit margin, operating expenses, operating income margin, taxes, and net margin \- as both dollar values and percentage of revenue. Select any fiscal year from the dropdown.

\!\[wf chart\](screenshots/wfchart.png)

#### **Operating Expenses Breakdown**

Donut chart showing the composition of operating expenses: R\&D, SG\&A, and depreciation and amortization \- with dollar amounts and percentages for any selected year.

\!\[donut\](screenshots/donut.png)

### **Balance Sheet**

Track assets, liabilities, and equity across years. The Balance Sheet Composition chart shows a stacked bar view of current assets, non-current assets, current liabilities, non-current liabilities, and shareholder equity \- with a toggle between dollar values and percentage composition.

\!\[bsheet\](screenshots/bsheet.png)

### **Cash Flow**

Operating cash flow, capital expenditures, free cash flow, financing activities, stock-based compensation \- all chartable with the same multi-company comparison and display mode options.

\!\[cflow\](screenshots/bsheet.png)

### 

### **Earnings**

Reported EPS over time, annual or quarterly, with the same comparison and toggle features as other financial charts.

\!\[earnings\](screenshots/earnings.png)

#### **Earnings Surprise Dot Chart**

A unique visualization showing estimated vs reported EPS for each quarter. Green filled dots for beats, red for misses, with connecting lines showing the surprise magnitude. Includes a beat count summary (e.g. "Beat estimates 12 of last 12 quarters") and a quarter range selector (8Q, 12Q, 20Q, 40Q, Max).

\!\[dotchart\](screenshots/dotchart.png)

### **Historical Table**

A spreadsheet-style view of any financial data across time. Toggle annual/quarterly, set the time range, enable YoY percentage change, compare against other tickers, and add section groups (Net Income, Other Income and Expenses, etc.) using the section chips. Click any chart icon to jump to the chart modal for that metric.

\!\[htable\](screenshots/htable.png)

### **Price vs Fundamentals**

An indexed overlay chart comparing stock price movement against a fundamental metric (Revenue, Net Income, EPS, Free Cash Flow, Operating Cash Flow, Total Assets, Shareholder Equity, or Total Debt). Both are indexed to 100 at the start of the selected period so their relative growth is directly comparable regardless of absolute scale. Includes a text insight below the chart summarizing whether price is outpacing fundamentals or vice versa. Supports Raw, Indexed, and Log display modes. Option can be found above the ticker price. 

\!\[PvsF\](screenshots/pvf.png)

### **Multi-Company Comparison**

#### **Scatter Compare**

Plot any two metrics from the entire stock universe against each other. Choose X and Y axes from valuation, profitability, growth, and dividend metrics. Filter by sector, industry, exchange, and market cap range. Quick-select presets: PE vs Profit Margin, Market Cap vs ROE, Dividend Yield vs PEG, PE vs ROE, Market Cap vs Dividend Yield. Toggle filters for dividend payers only and positive earnings only.

Each dot is a company \- hover to see ticker, name, and both metric values. Option can be found on the landing page. 

\!\[scompare\](screenshots/scompare.png)

\!\[sc\](screenshots/sc.png)

### **Peer Comparison**

Compare any stock against its industry, sector, or market-cap peers on 20+ financial metrics using histogram and boxplot.

#### **Box Plot**

See exactly where a stock falls in its peer distribution. The box shows Q1 to Q3 (the middle 50% of peers), whiskers show the full range excluding outliers, and the current stock is highlighted as a labeled dot. Summary stats show peer average, median, range, count, and the stock's percentile ranking. 

\!\[box\](screenshots/box.png)

#### **Histogram**

See the distribution shape \- how many peers fall in each value range. The bin containing the current stock is highlighted. Useful for spotting whether the distribution is normal, skewed, or has outliers. Both views include a ranked table of all peers sorted by the selected metric, with the current stock's row highlighted.

\!\[hist\](screenshots/hist.png)

### **Insider and Institutional Activity**

Visual summary of institutional investor behavior based on the latest filings. A horizontal bar chart shows how many institutions initiated new positions, increased, decreased, or sold out \- with a net sentiment score.

\!\[Inst\](screenshots/inst.png)

\!\[instact\](screenshots/instact.png)

\!\[insider\](screenshots/insider.png)

### **Market News**

Paginated news feed with articles across all covered stocks, deduplicated by article. Search by ticker or topic. Each article shows the headline, source, publication time, and a link to the full article.

\!\[news\](screenshots/news.png)

### **Ask Freysa (AI Chat)**

A natural-language interface powered by Claude. Ask questions about stocks, sectors, or the market in plain English.

Examples of questions you can ask:

* "What's Amazon's profit margin?"  
* "Compare Apple and Microsoft's revenue over the last 5 years"  
* "Which tech stocks have the highest ROE?"  
* "Show me all stocks with PE under 15 and dividend yield above 3%"

\!\[ai\](screenshots/ai.png)

---

## **Data Coverage**

| Category | What's included |
| :---- | :---- |
| Stocks | 6,670+ active US common stocks |
| Exchanges | NYSE, NASDAQ, NYSE ARCA, BATS, AMEX |
| Fundamentals | Income statement, balance sheet, cash flow \- 10+ years annual and quarterly |
| Earnings | Historical EPS with beat/miss tracking |
| Daily Prices | Adjusted OHLCV \- 20+ years of history per stock |
| Market Indices | S\&P 500, Dow Jones, Nasdaq Composite, Russell 2000, Nasdaq 100, VIX (Indices are currently inactive)  |
| News | Recent articles with per-ticker sentiment scores |
| Insider Transactions | SEC Form 4 filings \- insider buys and sells |
| Institutional Holdings | 13F filing data \- who owns what and how positions changed |
| Dividends | Full dividend payment history |
| Stock Splits | Split history with factor details |
| IPOs | Upcoming IPO calendar (currently inactive) |

---

## **Data Freshness**

| Data | Update frequency |
| :---- | :---- |
| Stock prices | Daily, after market close |
| Market indices | Daily, after market close |
| Company overview | Every few hours during market hours (Currently inactive) |
| News & sentiment | Continuous |
| Fundamentals | Nightly, with fiscal-date-aware scheduling |
| Insider transactions | Every 2 days |
| Institutional holdings | Every 30 days (matches 13F filing cadence) |
| Dividends | Every 2 days |
| Earnings calendar | Nightly |
| Market status | Every 30 minutes during market hours |

---

## © All rights reserved
