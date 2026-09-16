// User registration form.
// This screen validates the password-confirmation flow, calls the backend register
// endpoint, and then redirects the user to login after a successful account creation.

import { useState } from 'react';
import { register } from '../services/api';

// Define the props (data passed to this component)
interface RegisterProps {
  onRegisterSuccess: () => void;  // Function to call when registration succeeds
  onLoginClick: () => void;  // Function to call when user clicks "Login"
}

// The Register component
export const Register = ({ onRegisterSuccess, onLoginClick }: RegisterProps) => {
  // State variables (data that can change)
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  // Handle form submission
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();  // Prevent page reload
    
    // Clear previous errors
    setError('');
    
    // The UX should fail early if the form inputs are inconsistent.
    if (password !== confirmPassword) {
      setError('Passwords do not match');
      return;
    }
    
    // Validate password length, CAN MODIFY LATER
    if (password.length < 6) {
      setError('Password must be at least 6 characters');
      return;
    }
    
    setLoading(true);
    
    try {
      // Submit the new account to the backend so the user can later log in.
      await register(email, password);
      
      // Call the success callback (parent component will handle redirect)
      onRegisterSuccess();
    } catch (err: any) {
      // Handle errors
      setError(err.response?.data?.detail || 'Registration failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  // Render the UI (JSX = JavaScript XML)
  return (
    <div className="auth-card" style={styles.container}>
      <h1>Register</h1>
      
      {/* Error message display */}
      {error && <div style={styles.error}>{error}</div>}
      
      {/* Registration form */}
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
        
        {/* Confirm Password input */}
        <div style={styles.inputGroup}>
          <label htmlFor="confirmPassword">Confirm Password:</label>
          <input
            type="password"
            id="confirmPassword"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            required
            style={styles.input}
            placeholder="Confirm your password"
          />
        </div>
        
        {/* Submit button */}
        <button type="submit" style={styles.button} disabled={loading}>
          {loading ? 'Creating account...' : 'Register'}
        </button>
      </form>
      
      {/* Link to login */}
      <p style={styles.loginLink}>
        Already have an account?{' '}
        <span onClick={onLoginClick} style={styles.link}>
          Login here
        </span>
      </p>
    </div>
  );
};

// Styles (CSS-in-JS) - Same as Login for consistency
const styles = {
  container: {
    maxWidth: '400px',
    margin: '50px auto',
    padding: '20px',
    border: '1px solid #ddd',
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
    backgroundColor: '#28a745',  // Green for register (different from login blue)
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
  loginLink: {
    textAlign: 'center' as const,
    marginTop: '20px',
  },
  link: {
    color: '#007bff',
    cursor: 'pointer',
    textDecoration: 'underline',
  },
};

export default Register;
