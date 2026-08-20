// Top-level React application shell.
// This component decides whether the user is seeing the login/register flow or the
// main authenticated view. It is responsible for navigating between screens and for
// keeping the UI state aligned with the backend auth flow.

import { useState } from 'react';
import Login from './components/Login';
import Register from './components/Register';
import { getJobStatus, runSegmentation, uploadFile } from './services/api';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const defaultParameters = {
  thresholdMin: 0,
  thresholdMax: 255,
  intensity: 1,
  percentage: 100,
  pixelSize: 1,
  minSize: 100,
  smoothing: 0,
};

function App() {
  const [currentView, setCurrentView] = useState<'login' | 'register' | 'main'>('login');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [statusText, setStatusText] = useState('Upload an image to begin.');
  const [error, setError] = useState('');
  const [fileId, setFileId] = useState<number | null>(null);
  const [sourceImageUrl, setSourceImageUrl] = useState<string | null>(null);
  const [resultImageUrl, setResultImageUrl] = useState<string | null>(null);
  const [parameters, setParameters] = useState(defaultParameters);

  const pollJobStatus = async (jobId: string) => {
    try {
      const data = await getJobStatus(jobId);

      if (data.status === 'DONE' || data.status === 'completed') {
        const resultPath = data.results?.result_path;
        const fileName = resultPath ? resultPath.split('/').pop() : null;

        setStatusText('Processing finished. Result ready.');
        setProcessing(false);

        if (fileName) {
          setResultImageUrl(`${API_BASE_URL}/results/${fileName}`);
        }
        return;
      }

      setStatusText('Processing image...');
      window.setTimeout(() => {
        void pollJobStatus(jobId);
      }, 1500);
    } catch (pollError: any) {
      setError(pollError?.response?.data?.detail || 'Error checking job status.');
      setProcessing(false);
    }
  };

  const handleUpload = async () => {
    if (!selectedFile) {
      setError('Please choose an image first.');
      return;
    }

    setError('');
    setUploading(true);
    setStatusText('Uploading image...');
    setResultImageUrl(null);

    try {
      const response = await uploadFile(selectedFile);
      setFileId(response.file_id);
      setSourceImageUrl(URL.createObjectURL(selectedFile));
      setUploading(false);
      setStatusText('Image uploaded. Set the parameters, then click Process.');
    } catch (uploadError: any) {
      setError(uploadError?.response?.data?.detail || uploadError?.message || 'Upload failed.');
      setUploading(false);
    }
  };

  const handleProcess = async () => {
    if (fileId === null) {
      setError('Upload an image before processing it.');
      return;
    }

    setError('');
    setProcessing(true);
    setResultImageUrl(null);
    setStatusText('Analysis is running...');

    try {
      const response = await runSegmentation(fileId, parameters);
      await pollJobStatus(response.job_id);
    } catch (processError: any) {
      setError(processError?.response?.data?.detail || processError?.message || 'Processing failed.');
      setProcessing(false);
    }
  };

  const handleLoginSuccess = () => {
    setCurrentView('main');
    setError('');
    setSelectedFile(null);
    setResultImageUrl(null);
    setStatusText('Upload an image to begin.');
    setFileId(null);
    setSourceImageUrl(null);
    setParameters(defaultParameters);
  };

  const handleRegisterSuccess = () => {
    setCurrentView('login');
    alert('Registration successful! Please login.');
  };

  const handleLogout = () => {
    localStorage.removeItem('access_token');
    setCurrentView('login');
    setSelectedFile(null);
    setFileId(null);
    setSourceImageUrl(null);
    setResultImageUrl(null);
    setStatusText('Upload an image to begin.');
    setError('');
  };

  return (
    <div style={{ fontFamily: 'Arial, sans-serif', padding: '20px', minHeight: '100vh', backgroundColor: '#f8f9fa' }}>
      <h1 style={{ textAlign: 'center', color: '#007bff', fontSize: '32px', marginBottom: '30px' }}>
        BeadBuddy Web App
      </h1>

      {currentView === 'login' && (
        <Login
          onLoginSuccess={handleLoginSuccess}
          onRegisterClick={() => setCurrentView('register')}
        />
      )}

      {currentView === 'register' && (
        <Register
          onRegisterSuccess={handleRegisterSuccess}
          onLoginClick={() => setCurrentView('login')}
        />
      )}

      {currentView === 'main' && (
        <div style={{ maxWidth: '1100px', margin: '0 auto', textAlign: 'center' }}>
          <h2>Welcome to BeadBuddy!</h2>
          <p>Upload an image, configure the analysis, and process it.</p>

          <div className="workspace-panels" style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)', gap: '24px', margin: '30px 0', textAlign: 'left' }}>
            <section className="workspace-image-panel" style={{ padding: '20px', border: '1px solid #ddd', borderRadius: '8px', backgroundColor: '#fff' }}>
              <h3>Original image</h3>
              <div className="workspace-image-stage" style={{ display: 'grid', placeItems: 'center', borderRadius: '8px', overflow: 'hidden' }}>
                {sourceImageUrl ? <img className="workspace-image" src={sourceImageUrl} alt="Uploaded source" /> : <span style={{ color: '#aaa' }}>Your uploaded image will appear here</span>}
              </div>
            </section>

            <section className="workspace-image-panel" style={{ padding: '20px', border: '1px solid #ddd', borderRadius: '8px', backgroundColor: '#fff' }}>
              <h3>Processed image</h3>
              <div className="workspace-image-stage" style={{ display: 'grid', placeItems: 'center', borderRadius: '8px', overflow: 'hidden' }}>
                {processing && <div aria-label="Processing" style={{ width: '48px', height: '48px', border: '5px solid #777', borderTopColor: '#fff', borderRadius: '50%', animation: 'spin 1s linear infinite' }} />}
                {!processing && resultImageUrl && <img className="workspace-image" src={resultImageUrl} alt="Processed output" />}
                {!processing && !resultImageUrl && <span style={{ color: '#aaa' }}>Your result will appear here</span>}
              </div>
            </section>
          </div>

          <section className="workspace-controls" style={{ margin: '30px 0', padding: '20px', border: '1px solid #ddd', borderRadius: '8px', backgroundColor: '#fff', textAlign: 'left' }}>
            <label htmlFor="upload-input" style={{ display: 'block', marginBottom: '12px', fontWeight: 600 }}>
              Choose an image
            </label>
            <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '12px' }}>
              <input
                id="upload-input"
                type="file"
                accept="image/*"
                onChange={(event) => {
                  setSelectedFile(event.target.files?.[0] || null);
                  setFileId(null);
                  setSourceImageUrl(null);
                  setResultImageUrl(null);
                  setStatusText('Image selected. Click Upload image.');
                }}
              />
              <button
                onClick={handleUpload}
                disabled={!selectedFile || uploading}
                style={{ padding: '12px 24px', fontSize: '16px', backgroundColor: selectedFile && !uploading ? '#007bff' : '#6c757d', color: 'white', border: 'none', borderRadius: '4px', cursor: selectedFile && !uploading ? 'pointer' : 'not-allowed' }}
              >
                {uploading ? 'Uploading...' : 'Upload image'}
              </button>
              <button
                onClick={handleProcess}
                disabled={fileId === null || processing}
                style={{ padding: '12px 28px', fontSize: '16px', backgroundColor: fileId !== null && !processing ? '#198754' : '#6c757d', color: '#fff', border: 'none', borderRadius: '4px', cursor: fileId !== null && !processing ? 'pointer' : 'not-allowed' }}
              >
                {processing ? 'Processing...' : 'Process'}
              </button>
            </div>
          </section>

          <section style={{ margin: '30px 0', padding: '20px', border: '1px solid #ddd', borderRadius: '8px', backgroundColor: '#fff', textAlign: 'left' }}>
            <h3>Analysis parameters (dummy)</h3>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '16px' }}>
              {Object.entries(parameters).map(([name, value]) => (
                <label key={name} style={{ display: 'grid', gap: '6px', fontWeight: 600 }}>
                  {name.replace(/([A-Z])/g, ' $1').replace(/^./, (letter) => letter.toUpperCase())}
                  <input
                    type="number"
                    value={value}
                    onChange={(event) => setParameters((current) => ({ ...current, [name]: Number(event.target.value) }))}
                    disabled={processing}
                    style={{ padding: '10px', border: '1px solid #ccc', borderRadius: '4px' }}
                  />
                </label>
              ))}
            </div>
          </section>

          {error && <div style={{ backgroundColor: '#f8d7da', color: '#721c24', padding: '10px', borderRadius: '4px', marginBottom: '12px' }}>{error}</div>}
          <p style={{ marginTop: '12px', color: '#333' }}>{statusText}</p>

          <button
            onClick={handleLogout}
            style={{
              padding: '12px 24px',
              fontSize: '16px',
              backgroundColor: '#dc3545',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
              marginTop: '20px',
            }}
          >
            Logout
          </button>
        </div>
      )}
    </div>
  );
}

export default App;