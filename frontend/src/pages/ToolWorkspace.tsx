// Generic tool workspace: upload a stack, run the tool, browse slices, download.
// This is intentionally tool-agnostic - it only depends on the Tool metadata
// coming from the registry (name + parameter list), so a new tool that
// follows the standard contract (TIFF in, TIFF + metadata out) needs no new
// frontend page at all.
import { useRef, useState } from 'react';
import type { Tool } from '../types/tool';
import {
  downloadJobResult,
  getJobStatus,
  getResultSlice,
  getSourceSlice,
  runTool,
  uploadFile,
} from '../services/api';

interface ToolWorkspaceProps {
  tool: Tool;
  onBack: () => void;
}

const buildDefaultParameters = (tool: Tool): Record<string, number> =>
  Object.fromEntries(tool.parameters.map((parameter) => [parameter.name, parameter.default]));

const POLL_INTERVAL_MS = 1500;
const TERMINAL_STATUSES = new Set(['completed', 'failed']);

const ToolWorkspace = ({ tool, onBack }: ToolWorkspaceProps) => {
  const [uploading, setUploading] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [statusText, setStatusText] = useState('Upload a file to begin.');
  const [error, setError] = useState('');
  const [fileId, setFileId] = useState<number | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [sliceCount, setSliceCount] = useState(1);
  const [currentSlice, setCurrentSlice] = useState(0);
  const [downloadReady, setDownloadReady] = useState(false);
  const [sourceImageUrl, setSourceImageUrl] = useState<string | null>(null);
  const [resultImageUrl, setResultImageUrl] = useState<string | null>(null);
  const [parameters, setParameters] = useState<Record<string, number>>(() => buildDefaultParameters(tool));
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadSlice = async (sliceIndex: number, sourceId = fileId, resultId = jobId) => {
    if (sourceId !== null) {
      const sourceBlob = await getSourceSlice(sourceId, sliceIndex);
      setSourceImageUrl(URL.createObjectURL(sourceBlob));
    }
    if (resultId !== null && downloadReady) {
      const resultBlob = await getResultSlice(resultId, sliceIndex);
      setResultImageUrl(URL.createObjectURL(resultBlob));
    }
  };

  const pollJobStatus = async (pollingJobId: string) => {
    try {
      const data = await getJobStatus(pollingJobId);

      if (data.status === 'completed') {
        setStatusText('Processing finished. Result ready.');
        setProcessing(false);
        setJobId(pollingJobId);
        setDownloadReady(true);

        const resultBlob = await getResultSlice(pollingJobId, currentSlice);
        setResultImageUrl(URL.createObjectURL(resultBlob));
        return;
      }

      if (data.status === 'failed') {
        setError(data.error || 'Processing failed.');
        setStatusText('Processing failed.');
        setProcessing(false);
        return;
      }

      setStatusText(`Processing (${data.status})...`);
      window.setTimeout(() => {
        void pollJobStatus(pollingJobId);
      }, POLL_INTERVAL_MS);
    } catch (pollError: any) {
      setError(pollError?.response?.data?.detail || 'Error checking job status.');
      setProcessing(false);
    }
  };

  const uploadSelectedFile = async (file: File) => {
    setError('');
    setUploading(true);
    setStatusText('Uploading file...');
    setResultImageUrl(null);
    setJobId(null);
    setDownloadReady(false);

    try {
      const response = await uploadFile(file);
      setFileId(response.file_id);
      const nextSliceCount = response.slice_count || 1;
      const middleSlice = Math.floor(nextSliceCount / 2);
      setSliceCount(nextSliceCount);
      setCurrentSlice(middleSlice);
      const sourceBlob = await getSourceSlice(response.file_id, middleSlice);
      setSourceImageUrl(URL.createObjectURL(sourceBlob));
      setUploading(false);
      setStatusText('File uploaded. Set the parameters, then click Process.');
    } catch (uploadError: any) {
      setError(uploadError?.response?.data?.detail || uploadError?.message || 'Upload failed.');
      setUploading(false);
    }
  };

  const handleUpload = () => {
    fileInputRef.current?.click();
  };

  const handleProcess = async () => {
    if (fileId === null) {
      setError('Upload a file before processing it.');
      return;
    }

    setError('');
    setProcessing(true);
    setResultImageUrl(null);
    setStatusText('Analysis is running...');

    try {
      const response = await runTool(tool.id, fileId, parameters);
      setJobId(response.job_id);
      await pollJobStatus(response.job_id);
    } catch (processError: any) {
      setError(processError?.response?.data?.detail || processError?.message || 'Processing failed.');
      setProcessing(false);
    }
  };

  const handleSliceChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const sliceIndex = Number(event.target.value);
    setCurrentSlice(sliceIndex);
    try {
      await loadSlice(sliceIndex);
    } catch (sliceError: any) {
      setError(sliceError?.response?.data?.detail || 'Unable to load this slice.');
    }
  };

  const handleDownload = async () => {
    if (!jobId) return;

    try {
      const archive = await downloadJobResult(jobId);
      const downloadUrl = URL.createObjectURL(archive);
      const link = document.createElement('a');
      link.href = downloadUrl;
      link.download = `${tool.id}_${jobId}.zip`;
      link.click();
      URL.revokeObjectURL(downloadUrl);
    } catch (downloadError: any) {
      setError(downloadError?.response?.data?.detail || 'Download failed.');
    }
  };

  return (
    <div style={{ maxWidth: '1100px', margin: '0 auto', textAlign: 'center' }}>
      <h2>{tool.name}</h2>
      <p>Upload a file, configure the analysis, and process it.</p>
      <button className="back-to-tools" onClick={onBack} type="button">
        Back to tools
      </button>

      <div className="workspace-panels" style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)', gap: '24px', margin: '30px 0', textAlign: 'left' }}>
        <section className="workspace-image-panel" style={{ padding: '20px', border: '1px solid #ddd', borderRadius: '8px', backgroundColor: '#fff' }}>
          <h3>Original file</h3>
          <div className="workspace-image-stage" style={{ display: 'grid', placeItems: 'center', borderRadius: '8px', overflow: 'hidden' }}>
            {sourceImageUrl ? <img className="workspace-image" src={sourceImageUrl} alt="Uploaded source" /> : <span style={{ color: '#aaa' }}>Your uploaded file will appear here</span>}
          </div>
        </section>

        <section className="workspace-image-panel" style={{ padding: '20px', border: '1px solid #ddd', borderRadius: '8px', backgroundColor: '#fff' }}>
          <h3>Processed result</h3>
          <div className="workspace-image-stage" style={{ display: 'grid', placeItems: 'center', borderRadius: '8px', overflow: 'hidden' }}>
            {processing && <div aria-label="Processing" style={{ width: '48px', height: '48px', border: '5px solid #777', borderTopColor: '#fff', borderRadius: '50%', animation: 'spin 1s linear infinite' }} />}
            {!processing && resultImageUrl && <img className="workspace-image" src={resultImageUrl} alt="Processed output" />}
            {!processing && !resultImageUrl && <span style={{ color: '#aaa' }}>Your result will appear here</span>}
          </div>
        </section>
      </div>

      <div className="slice-controls">
        <label htmlFor="slice-slider">Slice {currentSlice + 1} of {sliceCount}</label>
        <input
          id="slice-slider"
          type="range"
          min="0"
          max={Math.max(0, sliceCount - 1)}
          value={currentSlice}
          onChange={(event) => void handleSliceChange(event)}
          disabled={fileId === null || uploading}
        />
      </div>

      <section className="workspace-controls" style={{ margin: '30px 0', padding: '20px', border: '1px solid #ddd', borderRadius: '8px', backgroundColor: '#fff', textAlign: 'left' }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '12px' }}>
          <input
            id="upload-input"
            ref={fileInputRef}
            type="file"
            accept={tool.accepted_extensions.join(',')}
            hidden
            onChange={(event) => {
              const file = event.target.files?.[0] || null;
              setFileId(null);
              setSourceImageUrl(null);
              setResultImageUrl(null);
              setDownloadReady(false);
              if (file) {
                void uploadSelectedFile(file);
              }
            }}
          />
          <button
            onClick={handleUpload}
            disabled={uploading}
            style={{ width: '150px', padding: '12px 24px', fontSize: '16px', backgroundColor: uploading ? '#6c757d' : '#007bff', color: 'white', border: 'none', borderRadius: '4px', cursor: uploading ? 'not-allowed' : 'pointer' }}
          >
            {uploading ? 'Uploading...' : 'Upload'}
          </button>
          <button
            onClick={handleProcess}
            disabled={fileId === null || processing}
            style={{ width: '150px', padding: '12px 28px', fontSize: '16px', backgroundColor: fileId !== null && !processing ? '#198754' : '#6c757d', color: '#fff', border: 'none', borderRadius: '4px', cursor: fileId !== null && !processing ? 'pointer' : 'not-allowed' }}
          >
            {processing ? 'Processing...' : 'Process'}
          </button>
          <button
            onClick={handleDownload}
            disabled={!downloadReady}
            style={{ width: '180px', padding: '12px 20px', fontSize: '16px', backgroundColor: downloadReady ? '#0d6efd' : '#6c757d', color: '#fff', border: 'none', borderRadius: '4px', cursor: downloadReady ? 'pointer' : 'not-allowed' }}
          >
            Download
          </button>
        </div>
      </section>

      {tool.parameters.length > 0 && (
        <section style={{ margin: '30px 0', padding: '20px', border: '1px solid #ddd', borderRadius: '8px', backgroundColor: '#fff', textAlign: 'left' }}>
          <h3>Analysis parameters</h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '16px' }}>
            {tool.parameters.map((parameter) => (
              <label key={parameter.name} style={{ display: 'grid', gap: '6px', fontWeight: 600 }}>
                {parameter.label}
                <input
                  type="number"
                  value={parameters[parameter.name]}
                  min={parameter.minimum ?? undefined}
                  max={parameter.maximum ?? undefined}
                  step={parameter.step}
                  onChange={(event) =>
                    setParameters((current) => ({ ...current, [parameter.name]: Number(event.target.value) }))
                  }
                  disabled={processing}
                  style={{ padding: '10px', border: '1px solid #ccc', borderRadius: '4px' }}
                />
              </label>
            ))}
          </div>
        </section>
      )}

      {error && <div style={{ backgroundColor: '#f8d7da', color: '#721c24', padding: '10px', borderRadius: '4px', marginBottom: '12px' }}>{error}</div>}
      <p style={{ marginTop: '12px', color: '#333' }}>{statusText}</p>
    </div>
  );
};

export default ToolWorkspace;

// Exported for tests / reuse if a tool ever needs to know when a job is done.
export const isTerminalStatus = (status: string) => TERMINAL_STATUSES.has(status);
