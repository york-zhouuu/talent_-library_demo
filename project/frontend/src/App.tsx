import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import TalentPools from './pages/TalentPools'
import PoolDetail from './pages/PoolDetail'
import Upload from './pages/Upload'
import Search from './pages/Search'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Search />} />
          <Route path="pools" element={<TalentPools />} />
          <Route path="pools/:id" element={<PoolDetail />} />
          <Route path="upload" element={<Upload />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
