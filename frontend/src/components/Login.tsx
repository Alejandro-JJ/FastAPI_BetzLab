// User login form.
// This component collects the email and password, calls the backend login endpoint,
// and stores the JWT token in browser storage so later requests can be authenticated.

import { useState } from 'react';
import { login, saveToken } from '../services/api';

// Define the props (data passed to this component)
interface LoginProps {
  onLoginSuccess: () => void;  // Function to call when login succeeds
  onRegisterClick: () => void;  // Function to call when user clicks "Register"
}

// The Login component
const Login = ({ onLoginSuccess, onRegisterClick }: LoginProps) => {
  // State variables (data that can change)
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  // Handle form submission
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();  // Prevent page reload
    
    // Clear previous errors
    setError('');
    setLoading(true);
    
    try {
      // Call the login API
      const response = await login(email, password);
      
      // Save the token to localStorage
      saveToken(response.access_token);
      
      // Call the success callback (parent component will handle redirect)
      onLoginSuccess();
    } catch (err: any) {
      // Handle errors
      setError(err.response?.data?.detail || 'Login failed. Please check your credentials.');
    } finally {
      setLoading(false);
    }
  };

  // Render the UI (JSX = JavaScript XML)
  return (
    <div style={styles.container}>
      <h1>Login</h1>
      
      {/* Error message display */}
      {error && <div style={styles.error}>{error}</div>}
      
      {/* Login form */}
      <form onSubmit={handleSubmit} style={styles.form}>
        {/* Email input */}
        <div style={styles.inputGroup}>
          <label htmlFor="email">Email:</label>
          <input
            type="email"
            id="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            style={styles.input}
            placeholder="Enter your email"
          />
        </div>
        
        {/* Password input */}
        <div style={styles.inputGroup}>
          <label htmlFor="password">Password:</label>
          <input
            type="password"
            id="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            style={styles.input}
            placeholder="Enter your password"
          />
        </div>
        
        {/* Submit button */}
        <button type="submit" style={styles.button} disabled={loading}>
          {loading ? 'Logging in...' : 'Login'}
        </button>
      </form>
      
      {/* Link to register */}
      <p style={styles.registerLink}>
        Don't have an account?{' '}
        <span onClick={onRegisterClick} style={styles.link}>
          Register here
        </span>
      </p>
    </div>
  );
};

// Styles (CSS-in-JS)
const styles = {
  container: {
    maxWidth: '400px',
    margin: '50px auto',
    padding: '20px',
    border: '1px solid #ffffffff',
    borderRadius: '8px',
    boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
  },
  form: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '15px',
  },
  inputGroup: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '5px',
  },
  input: {
    padding: '10px',
    fontSize: '16px',
    border: '1px solid #ccc',
    borderRadius: '4px',
  },
  button: {
    padding: '12px',
    fontSize: '16px',
    backgroundColor: '#007bff',
    color: 'white',
    border: 'none',
    borderRadius: '4px',
    cursor: 'pointer',
  },
  error: {
    padding: '10px',
    backgroundColor: '#f8d7da',
    color: '#721c24',
    borderRadius: '4px',
    marginBottom: '15px',
  },
  registerLink: {
    textAlign: 'center' as const,
    marginTop: '20px',
  },
  link: {
    color: '#007bff',
    cursor: 'pointer',
    textDecoration: 'underline',
  },
};

export default Login;