
import React, { useEffect, useState } from 'react'
import { fetchUsers, createUser } from './api'

const roles = [
  ['executive', 'Executive'],
  ['supervisor', 'Site Supervisor'],
  ['health_safety', 'Health & Safety Officer'],
  ['researcher', 'Researcher'],
  ['worker', 'Worker'],
  ['admin', 'System Admin'],
]

export default function AdminUsers() {
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [form, setForm] = useState({
    full_name: '',
    email: '',
    password: '',
    role: 'supervisor',
  })

  async function loadUsers() {
    setLoading(true)
    setError('')
    try {
      const data = await fetchUsers()
      setUsers(data.users || [])
    } catch (err) {
      setError(err.message || 'Could not load users.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadUsers()
  }, [])

  async function handleCreate(e) {
    e.preventDefault()
    setSaving(true)
    setError('')
    setSuccess('')

    try {
      await createUser(form)
      setSuccess('User account created successfully.')
      setForm({
        full_name: '',
        email: '',
        password: '',
        role: 'supervisor',
      })
      await loadUsers()
    } catch (err) {
      setError(err.message || 'Could not create user.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="content">
      <div className="welcome-row">
        <div>
          <div className="eyebrow">SYSTEM ADMINISTRATION</div>
          <h1>User Management</h1>
          <p className="muted">
            Create accounts and assign authorised workspace roles.
          </p>
        </div>
        <div className="demo-tag">ADMIN ONLY</div>
      </div>

      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-label">TOTAL ACCOUNTS</div>
          <strong>{users.length}</strong>
          <small>Registered platform users</small>
        </div>
        <div className="stat-card">
          <div className="stat-label">ACTIVE ACCOUNTS</div>
          <strong>{users.filter(u => u.active).length}</strong>
          <small>Accounts currently enabled</small>
        </div>
        <div className="stat-card">
          <div className="stat-label">ADMINISTRATORS</div>
          <strong>{users.filter(u => u.role === 'admin').length}</strong>
          <small>System administration accounts</small>
        </div>
      </div>

      <div className="section-heading">
        <div>
          <div className="eyebrow">ACCOUNT PROVISIONING</div>
          <h2>Create a user</h2>
        </div>
      </div>

      <div className="card" style={{ padding: 24, marginBottom: 28 }}>
        <form onSubmit={handleCreate}>
          <div className="form-grid">
            <div>
              <label>Full name</label>
              <input
                required
                value={form.full_name}
                onChange={e => setForm({...form, full_name: e.target.value})}
                placeholder="Enter full name"
              />
            </div>

            <div>
              <label>Work email</label>
              <input
                required
                type="email"
                value={form.email}
                onChange={e => setForm({...form, email: e.target.value})}
                placeholder="name@organisation.com"
              />
            </div>

            <div>
              <label>Temporary password</label>
              <input
                required
                type="password"
                minLength={10}
                value={form.password}
                onChange={e => setForm({...form, password: e.target.value})}
                placeholder="At least 10 characters"
              />
            </div>

            <div>
              <label>Assign role</label>
              <select
                value={form.role}
                onChange={e => setForm({...form, role: e.target.value})}
              >
                {roles.map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </div>
          </div>

          {error && <p style={{color:'#c62828'}}>{error}</p>}
          {success && <p style={{color:'#087f5b'}}>{success}</p>}

          <button className="btn btn-dark" type="submit" disabled={saving}>
            {saving ? 'Creating account…' : 'Create user account'}
          </button>
        </form>
      </div>

      <div className="section-heading">
        <div>
          <div className="eyebrow">REGISTERED ACCOUNTS</div>
          <h2>Platform users</h2>
        </div>
        <button className="btn btn-dark" onClick={loadUsers}>
          Refresh
        </button>
      </div>

      <div className="card" style={{padding:20, overflowX:'auto'}}>
        {loading ? (
          <p>Loading accounts…</p>
        ) : users.length === 0 ? (
          <p>No user accounts found.</p>
        ) : (
          <table style={{width:'100%', borderCollapse:'collapse', textAlign:'left'}}>
            <thead>
              <tr>
                <th style={{padding:12}}>Name</th>
                <th style={{padding:12}}>Email</th>
                <th style={{padding:12}}>Role</th>
                <th style={{padding:12}}>Status</th>
                <th style={{padding:12}}>Created</th>
              </tr>
            </thead>
            <tbody>
              {users.map(user => (
                <tr key={user.id}>
                  <td style={{padding:12}}>{user.full_name}</td>
                  <td style={{padding:12}}>{user.email}</td>
                  <td style={{padding:12}}>
                    {roles.find(r => r[0] === user.role)?.[1] || user.role}
                  </td>
                  <td style={{padding:12}}>
                    {user.active ? 'Active' : 'Inactive'}
                  </td>
                  <td style={{padding:12}}>
                    {user.created_at
                      ? new Date(user.created_at).toLocaleDateString()
                      : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  )
}
