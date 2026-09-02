import { useEffect, useState } from 'react'

function App() {
  const [stocks, setStocks] = useState([])

  useEffect(() => {
    fetch('http://127.0.0.1:8000/stocks')
      .then((response) => response.json())
      .then((data) => setStocks(data.stocks))
      .catch((error) => console.error('Error fetching stocks:', error))
  }, [])

  return (
    <div>
      <h1>TradeX</h1>
      <h2>Available Stocks</h2>
      <ul>
        {stocks.map((stock) => (
          <li key={stock.symbol}>
            {stock.symbol} — {stock.company_name} — ₹{stock.current_price}
          </li>
        ))}
      </ul>
    </div>
  )
}

export default App