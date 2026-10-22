import { useEffect, useMemo, useRef, useState } from 'react';
import type { Tool } from '../types/tool';
import {
  downloadJobResult,
  getJobArtifact,
  getJobStatus,
  getResultVectorSlice,
  getSourceSlice,
  rerenderJobPlot,
  runTool,
  uploadFile,
  type VectorSliceResponse,
} from '../services/api';

interface TractionForceWorkspaceProps {
  tool: Tool;
  onBack: () => void;
}

const buildDefaultParameters = (tool: Tool): Record<string, number> =>
  Object.fromEntries(tool.parameters.map((parameter) => [parameter.name, parameter.default]));

const POLL_INTERVAL_MS = 1500;

const clamp01 = (value: number) => Math.min(1, Math.max(0, value));

const jetColor = (value: number): [number, number, number] => {
  const x = clamp01(value);
  const r = clamp01(1.5 - Math.abs(4 * x - 3));
  const g = clamp01(1.5 - Math.abs(4 * x - 2));
  const b = clamp01(1.5 - Math.abs(4 * x - 1));
  return [Math.round(r * 255), Math.round(g * 255), Math.round(b * 255)];
};

const viridisColor = (value: number): [number, number, number] => {
  const x = clamp01(value);
  const anchors: Array<[number, number, number]> = [
    [68, 1, 84],
    [59, 82, 139],
    [33, 145, 140],
    [94, 201, 98],
    [253, 231, 37],
  ];
  const scaled = x * (anchors.length - 1);
  const i0 = Math.floor(scaled);
  const i1 = Math.min(anchors.length - 1, i0 + 1);
  const t = scaled - i0;
  const c0 = anchors[i0];
  const c1 = anchors[i1];
  return [
    Math.round(c0[0] + (c1[0] - c0[0]) * t),
    Math.round(c0[1] + (c1[1] - c0[1]) * t),
    Math.round(c0[2] + (c1[2] - c0[2]) * t),
  ];
};

const infernoColor = (value: number): [number, number, number] => {
  const x = clamp01(value);
  const anchors: Array<[number, number, number]> = [
    [0, 0, 4],
    [87, 15, 109],
    [187, 55, 84],
    [249, 142, 8],
    [252, 255, 164],
  ];
  const scaled = x * (anchors.length - 1);
  const i0 = Math.floor(scaled);
  const i1 = Math.min(anchors.length - 1, i0 + 1);
  const t = scaled - i0;
  const c0 = anchors[i0];
  const c1 = anchors[i1];
  return [
    Math.round(c0[0] + (c1[0] - c0[0]) * t),
    Math.round(c0[1] + (c1[1] - c0[1]) * t),
    Math.round(c0[2] + (c1[2] - c0[2]) * t),
  ];
};

const turboColor = (value: number): [number, number, number] => {
  const x = clamp01(value);
  const anchors: Array<[number, number, number]> = [
    [48, 18, 59],
    [50, 115, 220],
    [53, 183, 121],
    [253, 231, 37],
    [180, 4, 38],
  ];
  const scaled = x * (anchors.length - 1);
  const i0 = Math.floor(scaled);
  const i1 = Math.min(anchors.length - 1, i0 + 1);
  const t = scaled - i0;
  const c0 = anchors[i0];
  const c1 = anchors[i1];
  return [
    Math.round(c0[0] + (c1[0] - c0[0]) * t),
    Math.round(c0[1] + (c1[1] - c0[1]) * t),
    Math.round(c0[2] + (c1[2] - c0[2]) * t),
  ];
};

const getColormap = (name: string) => {
  if (name === 'viridis') return viridisColor;
  if (name === 'inferno') return infernoColor;
  if (name === 'turbo') return turboColor;
  return jetColor;
};

const TractionForceWorkspace = ({ tool, onBack }: TractionForceWorkspaceProps) => {
  const [beforeUploading, setBeforeUploading] = useState(false);
  const [afterUploading, setAfterUploading] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [statusText, setStatusText] = useState('Upload both before and after images to begin.');
  const [error, setError] = useState('');

  const [beforeFileId, setBeforeFileId] = useState<number | null>(null);
  const [afterFileId, setAfterFileId] = useState<number | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);

  const [sliceCount, setSliceCount] = useState(1);
  const [currentSlice, setCurrentSlice] = useState(0);
  const [downloadReady, setDownloadReady] = useState(false);

  const [beforeImageUrl, setBeforeImageUrl] = useState<string | null>(null);
  const [afterImageUrl, setAfterImageUrl] = useState<string | null>(null);
  const [matplotlibImageUrl, setMatplotlibImageUrl] = useState<string | null>(null);
  const [displacementPlotUrl, setDisplacementPlotUrl] = useState<string | null>(null);
  const [tractionPlotUrl, setTractionPlotUrl] = useState<string | null>(null);
  const [vectorSlice, setVectorSlice] = useState<VectorSliceResponse | null>(null);
  const [vectorLoading, setVectorLoading] = useState(false);
  const [vectorArtifactReady, setVectorArtifactReady] = useState(false);

  const [resultSummary, setResultSummary] = useState<Record<string, unknown> | null>(null);
  const [parameters, setParameters] = useState<Record<string, number>>(() => buildDefaultParameters(tool));

  const [dimensionMode, setDimensionMode] = useState<'xy' | 'xyt' | 'xyz' | 'xyzct'>('xyt');
  const [displacementMethod, setDisplacementMethod] = useState<'dft' | 'elastix' | 'optical_flow' | 'elastix3d'>('dft');
  const [plotMode, setPlotMode] = useState<'magnitude' | 'field' | 'both'>('magnitude');
  const [colormapName, setColormapName] = useState<'jet' | 'viridis' | 'inferno' | 'turbo'>('jet');
  const [showScaleBar, setShowScaleBar] = useState(true);
  const [quiverStride, setQuiverStride] = useState(1);
  const [quiverLengthScale, setQuiverLengthScale] = useState(1);
  const [quiverSizeScale, setQuiverSizeScale] = useState(1);
  const [opticalFlowRadius, setOpticalFlowRadius] = useState(30);
  const [rigidAlignCrop, setRigidAlignCrop] = useState(true);

  const [cropEnabled, setCropEnabled] = useState(false);
  const [cropX0, setCropX0] = useState(0);
  const [cropY0, setCropY0] = useState(0);
  const [cropW, setCropW] = useState(256);
  const [cropH, setCropH] = useState(256);

  const [displacementReady, setDisplacementReady] = useState(false);
  const [lastDisplacementMethod, setLastDisplacementMethod] = useState<string>('none');
  const [tractionReady, setTractionReady] = useState(false);
  const [lastStage, setLastStage] = useState<'none' | 'displacement' | 'traction'>('none');
  const [processingStage, setProcessingStage] = useState<'none' | 'displacement' | 'traction'>('none');
  const [liveReplotting, setLiveReplotting] = useState(false);

  const beforeInputRef = useRef<HTMLInputElement>(null);
  const afterInputRef = useRef<HTMLInputElement>(null);
  const vectorCanvasRef = useRef<HTMLCanvasElement>(null);

  const vectorArtifactAvailable = vectorArtifactReady;

  const colorbarGradient = useMemo(() => {
    const colorAt = getColormap(colormapName);
    return `linear-gradient(to top, ${Array.from({ length: 7 }, (_, i) => {
      const t = i / 6;
      const [r, g, b] = colorAt(t);
      return `rgb(${r}, ${g}, ${b}) ${Math.round(t * 100)}%`;
    }).join(', ')})`;
  }, [colormapName]);

  const maxDisplayMagnitude = useMemo(() => {
    if (!vectorSlice) return 0;
    const rawMax = Math.max(...vectorSlice.magnitude.flat());
    const scale = Number(vectorSlice.scale_hint || 1);
    return rawMax * scale;
  }, [vectorSlice]);

  const displayUnit = useMemo(() => {
    if (!vectorSlice) return 'a.u.';
    if (vectorSlice.unit === 'pixels' && Number(vectorSlice.scale_hint || 1) !== 1) {
      return 'um';
    }
    return vectorSlice.unit;
  }, [vectorSlice]);

  const loadVectorSlice = async (targetJobId: string, sliceIndex: number) => {
    try {
      setVectorLoading(true);
      const data = await getResultVectorSlice(targetJobId, sliceIndex, Math.max(1, quiverStride));
      setVectorSlice(data);
    } catch {
      setVectorSlice(null);
    } finally {
      setVectorLoading(false);
    }
  };

  const getMatplotlibArtifactName = (summary: any, sliceIndex: number): string | null => {
    const artifactKeys = summary?.artifact_object_keys;
    if (!artifactKeys || typeof artifactKeys !== 'object') return null;
    const sliceKey = `matplotlib_plot_slice_${String(sliceIndex).padStart(4, '0')}`;
    if (artifactKeys[sliceKey]) return sliceKey;
    if (sliceIndex === 0 && artifactKeys.matplotlib_plot) return 'matplotlib_plot';
    return null;
  };

  const getStageArtifactName = (summary: any, stage: 'displacement' | 'traction', sliceIndex: number): string | null => {
    const artifactKeys = summary?.artifact_object_keys;
    if (!artifactKeys || typeof artifactKeys !== 'object') return null;
    const sliceKey = `matplotlib_${stage}_slice_${String(sliceIndex).padStart(4, '0')}`;
    if (artifactKeys[sliceKey]) return sliceKey;
    const firstKey = `matplotlib_${stage}_plot`;
    if (sliceIndex === 0 && artifactKeys[firstKey]) return firstKey;
    return null;
  };

  const loadStageMatplotlibPlot = async (
    targetJobId: string,
    summary: any,
    stage: 'displacement' | 'traction',
    sliceIndex: number,
  ): Promise<string | null> => {
    const artifactName = getStageArtifactName(summary, stage, sliceIndex);
    if (!artifactName) return null;
    try {
      const blob = await getJobArtifact(targetJobId, artifactName);
      return URL.createObjectURL(blob);
    } catch {
      return null;
    }
  };

  const loadMatplotlibPlot = async (targetJobId: string, summary: any, sliceIndex: number): Promise<boolean> => {
    const artifactName = getMatplotlibArtifactName(summary, sliceIndex);
    if (!artifactName) {
      setMatplotlibImageUrl(null);
      return false;
    }
    try {
      const blob = await getJobArtifact(targetJobId, artifactName);
      setMatplotlibImageUrl(URL.createObjectURL(blob));
      return true;
    } catch {
      setMatplotlibImageUrl(null);
      return false;
    }
  };

  useEffect(() => {
    const canvas = vectorCanvasRef.current;
    if (!canvas || !vectorSlice) return;
    const isTractionPreview = lastStage === 'traction';

    const rows = vectorSlice.magnitude.length;
    const cols = vectorSlice.magnitude[0]?.length || 0;
    if (rows === 0 || cols === 0) return;

    canvas.width = cols;
    canvas.height = rows;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const imageData = ctx.createImageData(cols, rows);
    const displayScale = Number(vectorSlice.scale_hint || 1);
    const u = vectorSlice.u;
    const v = vectorSlice.v;
    const magnitudeScaled: number[][] = Array.from({ length: rows }, () => Array.from({ length: cols }, () => 0));
    let maxMag = 1e-10;

    for (let y = 0; y < rows; y += 1) {
      for (let x = 0; x < cols; x += 1) {
        const uu = (u[y]?.[x] ?? 0) * displayScale;
        const vv = (v[y]?.[x] ?? 0) * displayScale;
        const norm = Math.sqrt(uu * uu + vv * vv);
        magnitudeScaled[y][x] = norm;
        if (norm > maxMag) maxMag = norm;
      }
    }

    const colorAt = getColormap(colormapName);

    for (let y = 0; y < rows; y += 1) {
      for (let x = 0; x < cols; x += 1) {
        // Streamlit uses origin='lower', so flip Y for canvas display.
        const offset = ((rows - 1 - y) * cols + x) * 4;
        const t = magnitudeScaled[y][x] / maxMag;
        const [r, g, b] = colorAt(t);
        if (plotMode === 'field' && !isTractionPreview) {
          imageData.data[offset] = 245;
          imageData.data[offset + 1] = 248;
          imageData.data[offset + 2] = 252;
          imageData.data[offset + 3] = 255;
        } else {
          imageData.data[offset] = r;
          imageData.data[offset + 1] = g;
          imageData.data[offset + 2] = b;
          imageData.data[offset + 3] = 255;
        }
      }
    }
    ctx.putImageData(imageData, 0, 0);

    if (plotMode === 'field' || plotMode === 'both' || lastStage === 'traction') {
      // approximate matplotlib quiver autoscaling in screen space
      const vectorScale = Math.max(0.5, Math.min(24, Math.min(rows, cols) * 0.38 / Math.max(1e-8, maxMag)));
      const quiverWidth = Math.max(0.9, Math.min(5.0, 0.9 * quiverSizeScale));
      const headSize = Math.max(4, Math.min(18, Math.round(4.5 * quiverSizeScale)));
      ctx.lineWidth = quiverWidth;

      for (let y = 0; y < rows; y += 1) {
        for (let x = 0; x < cols; x += 1) {
          if ((x % Math.max(1, quiverStride)) !== 0 || (y % Math.max(1, quiverStride)) !== 0) {
            continue;
          }
          const uu = u[y][x];
          const vv = v[y][x];
          const length = Math.sqrt(uu * uu + vv * vv);
          if (!Number.isFinite(length) || length < 1e-7) continue;
          const uuScaled = uu * displayScale;
          const vvScaled = vv * displayScale;
          const x0 = x + 0.5;
          const y0 = (rows - 1 - y) + 0.5;
          const dx = uuScaled * vectorScale * Math.max(0.1, quiverLengthScale);
          const dy = vvScaled * vectorScale * Math.max(0.1, quiverLengthScale);

          if (isTractionPreview || plotMode === 'both') {
            ctx.strokeStyle = '#ffffff';
            ctx.fillStyle = '#ffffff';
          } else {
            const normScaled = Math.sqrt(uuScaled * uuScaled + vvScaled * vvScaled);
            const [r, g, b] = colorAt(normScaled / maxMag);
            const c = `rgb(${r}, ${g}, ${b})`;
            ctx.strokeStyle = c;
            ctx.fillStyle = c;
          }
          const angle = Math.atan2(-dy, dx);
          const x1 = x0 + dx;
          const y1 = y0 - dy;

          ctx.beginPath();
          ctx.moveTo(x0, y0);
          ctx.lineTo(x1, y1);
          ctx.stroke();

          ctx.beginPath();
          ctx.moveTo(x1, y1);
          ctx.lineTo(x1 - headSize * Math.cos(angle - Math.PI / 6), y1 - headSize * Math.sin(angle - Math.PI / 6));
          ctx.lineTo(x1 - headSize * Math.cos(angle + Math.PI / 6), y1 - headSize * Math.sin(angle + Math.PI / 6));
          ctx.closePath();
          ctx.fill();
        }
      }
    }

    if (showScaleBar) {
      const umPerPixel = Number(parameters.mue2pix ?? 0.0772) * Math.max(1, vectorSlice.stride);
      const targetUm = 10;
      const barPx = Math.max(8, Math.min(Math.floor(cols * 0.4), Math.round(targetUm / Math.max(1e-8, umPerPixel))));
      const labelUm = barPx * umPerPixel;

      const y = rows - 8;
      const x0 = 8;
      const x1 = x0 + barPx;

      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(x0, y);
      ctx.lineTo(x1, y);
      ctx.stroke();

      ctx.fillStyle = '#ffffff';
      ctx.font = '8px sans-serif';
      ctx.fillText(`${labelUm.toFixed(1)} um`, x0, Math.max(9, y - 2));
    }
  }, [vectorSlice, plotMode, colormapName, quiverStride, quiverLengthScale, quiverSizeScale, showScaleBar, parameters.mue2pix, lastStage]);

  useEffect(() => {
    if (!jobId || !downloadReady || !vectorArtifactAvailable) return;
    void loadVectorSlice(jobId, currentSlice);
  }, [jobId, downloadReady, currentSlice, quiverStride, vectorArtifactAvailable]);

  const pollJobStatus = async (pollingJobId: string) => {
    try {
      const data = await getJobStatus(pollingJobId);

      if (data.status === 'completed') {
        setStatusText('Processing finished. Result ready.');
        setProcessing(false);
        setProcessingStage('none');
        setDownloadReady(true);
        setJobId(pollingJobId);

        if (data.summary) {
          setResultSummary(data.summary);
        }

        if (data.summary) {
          await loadMatplotlibPlot(pollingJobId, data.summary, currentSlice);

          const displacementUrl = await loadStageMatplotlibPlot(pollingJobId, data.summary, 'displacement', currentSlice);
          const tractionUrl = await loadStageMatplotlibPlot(pollingJobId, data.summary, 'traction', currentSlice);
          setDisplacementPlotUrl(displacementUrl);
          setTractionPlotUrl(tractionUrl);
        }
        if (data.summary?.artifact_object_keys?.vector_fields) {
          setVectorArtifactReady(true);
          await loadVectorSlice(pollingJobId, currentSlice);
        } else {
          setVectorArtifactReady(false);
          setVectorSlice(null);
        }
        return;
      }

      if (data.status === 'failed') {
        setError(data.error || 'Processing failed.');
        setStatusText('Processing failed.');
        setProcessing(false);
        setProcessingStage('none');
        return;
      }

      setStatusText(`Processing (${data.status})...`);
      window.setTimeout(() => {
        void pollJobStatus(pollingJobId);
      }, POLL_INTERVAL_MS);
    } catch (pollError: any) {
      setError(pollError?.response?.data?.detail || 'Error checking job status.');
      setProcessing(false);
      setProcessingStage('none');
    }
  };

  const uploadBeforeFile = async (file: File) => {
    setError('');
    setBeforeUploading(true);
    setStatusText('Uploading before image...');

    try {
      const response = await uploadFile(file);
      setBeforeFileId(response.file_id);
      setDisplacementReady(false);
      setTractionReady(false);
      setLastStage('none');
      setMatplotlibImageUrl(null);
      setDisplacementPlotUrl(null);
      setTractionPlotUrl(null);
      setVectorSlice(null);
      setVectorArtifactReady(false);
      setJobId(null);

      const nextSliceCount = response.slice_count || 1;
      const middleSlice = Math.floor(nextSliceCount / 2);
      setSliceCount(nextSliceCount);
      setCurrentSlice(middleSlice);

      const blob = await getSourceSlice(response.file_id, middleSlice);
      setBeforeImageUrl(URL.createObjectURL(blob));

      setBeforeUploading(false);
      setStatusText(afterFileId === null ? 'Before image uploaded. Upload after image next.' : 'Both images uploaded. Configure and process.');
    } catch (uploadError: any) {
      setError(uploadError?.response?.data?.detail || uploadError?.message || 'Before upload failed.');
      setBeforeUploading(false);
    }
  };

  const uploadAfterFile = async (file: File) => {
    setError('');
    setAfterUploading(true);
    setStatusText('Uploading after image...');

    try {
      const response = await uploadFile(file);
      setAfterFileId(response.file_id);
      setDisplacementReady(false);
      setTractionReady(false);
      setLastStage('none');
      setMatplotlibImageUrl(null);
      setDisplacementPlotUrl(null);
      setTractionPlotUrl(null);
      setVectorSlice(null);
      setVectorArtifactReady(false);
      setJobId(null);
      const blob = await getSourceSlice(response.file_id, 0);
      setAfterImageUrl(URL.createObjectURL(blob));

      setAfterUploading(false);
      setStatusText(beforeFileId === null ? 'After image uploaded. Upload before image next.' : 'Both images uploaded. Configure and process.');
    } catch (uploadError: any) {
      setError(uploadError?.response?.data?.detail || uploadError?.message || 'After upload failed.');
      setAfterUploading(false);
    }
  };

  const runStage = async (stage: 'displacement' | 'traction', forcedMethod?: 'dft' | 'elastix' | 'optical_flow' | 'elastix3d') => {
    if (beforeFileId === null || afterFileId === null) {
      setError('Upload both before and after images before processing.');
      return;
    }

    if (stage === 'traction' && !displacementReady) {
      setError('Run displacement first (DFT, Elastix, Optical Flow, or Elastix 3D).');
      return;
    }

    setError('');
    setProcessing(true);
    setProcessingStage(stage);
    setResultSummary(null);
    setDownloadReady(false);
    if (stage === 'traction') {
      setTractionPlotUrl(null);
    } else {
      setDisplacementPlotUrl(null);
      setTractionPlotUrl(null);
    }
    setStatusText(stage === 'displacement' ? 'Running displacement stage...' : 'Running traction stage...');

    try {
      const method = forcedMethod || displacementMethod;
      const payload: Record<string, unknown> = {
        ...parameters,
        after_file_id: afterFileId,
        dimension_mode: dimensionMode,
        displacement_method: method,
        run_traction: stage === 'traction',
        workflow_stage: stage,
        preview_mode: stage === 'traction' ? 'both' : plotMode,
        plot_colormap: colormapName,
        show_scale_bar: showScaleBar,
        quiver_stride: quiverStride,
        plot_quiver_length_scale: quiverLengthScale,
        plot_quiver_size_scale: quiverSizeScale,
        optical_flow_radius: opticalFlowRadius,
        crop_enabled: cropEnabled,
        rigid_align_crop: rigidAlignCrop,
      };

      if (cropEnabled) {
        payload.crop_x0 = cropX0;
        payload.crop_y0 = cropY0;
        payload.crop_w = cropW;
        payload.crop_h = cropH;
      }

      const response = await runTool(tool.id, beforeFileId, payload);
      setJobId(response.job_id);
      await pollJobStatus(response.job_id);

      if (stage === 'displacement') {
        setDisplacementReady(true);
        setTractionReady(false);
        setLastDisplacementMethod(method);
        setLastStage('displacement');
      } else {
        setTractionReady(true);
        setLastStage('traction');
      }
    } catch (processError: any) {
      setError(processError?.response?.data?.detail || processError?.message || 'Processing failed.');
      setProcessing(false);
      setProcessingStage('none');
    }
  };

  const clearAllData = () => {
    setError('');
    setStatusText('Upload both before and after images to begin.');
    setBeforeFileId(null);
    setAfterFileId(null);
    setJobId(null);
    setSliceCount(1);
    setCurrentSlice(0);
    setDownloadReady(false);
    setBeforeImageUrl(null);
    setAfterImageUrl(null);
    setMatplotlibImageUrl(null);
    setDisplacementPlotUrl(null);
    setTractionPlotUrl(null);
    setVectorSlice(null);
    setVectorArtifactReady(false);
    setResultSummary(null);
    setDisplacementReady(false);
    setTractionReady(false);
    setLastDisplacementMethod('none');
    setLastStage('none');
    setProcessingStage('none');
    setDimensionMode('xyt');
    setDisplacementMethod('dft');
    setPlotMode('magnitude');
    setColormapName('jet');
    setShowScaleBar(true);
    setQuiverStride(1);
    setQuiverLengthScale(1);
    setQuiverSizeScale(1);
    setOpticalFlowRadius(30);
    setCropEnabled(false);
    setCropX0(0);
    setCropY0(0);
    setCropW(256);
    setCropH(256);
    setRigidAlignCrop(true);
    setParameters(buildDefaultParameters(tool));
  };

  const handleSliceChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const sliceIndex = Number(event.target.value);
    setCurrentSlice(sliceIndex);

    try {
      if (beforeFileId !== null) {
        const beforeBlob = await getSourceSlice(beforeFileId, sliceIndex);
        setBeforeImageUrl(URL.createObjectURL(beforeBlob));
      }
      if (jobId && downloadReady) {
        await loadMatplotlibPlot(jobId, resultSummary, sliceIndex);
        if (resultSummary) {
          const displacementUrl = await loadStageMatplotlibPlot(jobId, resultSummary, 'displacement', sliceIndex);
          const tractionUrl = await loadStageMatplotlibPlot(jobId, resultSummary, 'traction', sliceIndex);
          setDisplacementPlotUrl(displacementUrl);
          setTractionPlotUrl(tractionUrl);
        }
      }
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

  useEffect(() => {
    if (!jobId || !downloadReady || processing || !resultSummary || lastStage === 'none') return;

    let cancelled = false;
    const run = async () => {
      try {
        setLiveReplotting(true);
        const sharedParams = {
          preview_mode: plotMode,
          plot_colormap: colormapName,
          quiver_stride: quiverStride,
          show_scale_bar: showScaleBar,
          plot_resolution_scale: 2.5,
          plot_quiver_length_scale: quiverLengthScale,
          plot_quiver_size_scale: quiverSizeScale,
        } as const;

        const displacementBlob = await rerenderJobPlot(jobId, 'displacement', currentSlice, sharedParams);
        if (cancelled) return;
        setDisplacementPlotUrl(URL.createObjectURL(displacementBlob));

        if (lastStage === 'traction') {
          const tractionBlob = await rerenderJobPlot(jobId, 'traction', currentSlice, {
            ...sharedParams,
            preview_mode: 'both',
          });
          if (cancelled) return;
          setTractionPlotUrl(URL.createObjectURL(tractionBlob));
        }
      } catch {
        // Keep existing plots if live re-render fails.
      } finally {
        if (!cancelled) setLiveReplotting(false);
      }
    };

    void run();
    return () => {
      cancelled = true;
    };
  }, [
    jobId,
    downloadReady,
    processing,
    resultSummary,
    lastStage,
    currentSlice,
    plotMode,
    colormapName,
    quiverStride,
    quiverLengthScale,
    quiverSizeScale,
    showScaleBar,
  ]);

  return (
    <div style={{ maxWidth: 'calc(100vw - 28px)', margin: '0 auto', textAlign: 'center' }}>
      <h2>{tool.name}</h2>
      <p>Follow this workflow from top to bottom, like the original Streamlit tool.</p>
      <button className="back-to-tools" onClick={onBack} type="button">
        Back to tools
      </button>

      <div className="tfm-layout" style={{ marginTop: '20px' }}>
        <aside className="tfm-sidebar">
          <section style={{ margin: '0 0 16px', padding: '20px', border: '1px solid #ddd', borderRadius: '8px', backgroundColor: '#fff', textAlign: 'left' }}>
            <h3>Step 1. Upload images</h3>
            <p style={{ marginTop: 0, color: '#5b6f86' }}>Before Image = moving/timelapse input, After Image = reference/static input.</p>
            <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
              <input
                ref={beforeInputRef}
                type="file"
                accept={tool.accepted_extensions.join(',')}
                hidden
                onChange={(event) => {
                  const file = event.target.files?.[0] || null;
                  if (file) void uploadBeforeFile(file);
                }}
              />
              <button
                onClick={() => beforeInputRef.current?.click()}
                type="button"
                disabled={beforeUploading || processing}
                style={{ width: '190px', padding: '12px 20px', backgroundColor: beforeUploading ? '#6c757d' : '#007bff', color: '#fff', border: 'none', borderRadius: '4px' }}
              >
                {beforeUploading ? 'Uploading before...' : 'Upload Before Image'}
              </button>

              <input
                ref={afterInputRef}
                type="file"
                accept={tool.accepted_extensions.join(',')}
                hidden
                onChange={(event) => {
                  const file = event.target.files?.[0] || null;
                  if (file) void uploadAfterFile(file);
                }}
              />
              <button
                onClick={() => afterInputRef.current?.click()}
                type="button"
                disabled={afterUploading || processing}
                style={{ width: '190px', padding: '12px 20px', backgroundColor: afterUploading ? '#6c757d' : '#007bff', color: '#fff', border: 'none', borderRadius: '4px' }}
              >
                {afterUploading ? 'Uploading after...' : 'Upload After Image'}
              </button>
            </div>
          </section>

          <section style={{ margin: '0 0 16px', padding: '20px', border: '1px solid #ddd', borderRadius: '8px', backgroundColor: '#fff', textAlign: 'left' }}>
            <h3>Step 2. Dimensionality and displacement setup</h3>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '16px' }}>
              <label style={{ display: 'grid', gap: '6px' }}>
                Dimension mode
                <select value={dimensionMode} onChange={(event) => setDimensionMode(event.target.value as 'xy' | 'xyt' | 'xyz' | 'xyzct')}>
                  <option value="xy">2D (xy)</option>
                  <option value="xyt">Timelapse (xyt)</option>
                  <option value="xyz">3D (xyz)</option>
                  <option value="xyzct">4D (xyzct)</option>
                </select>
              </label>

              <label style={{ display: 'grid', gap: '6px' }}>
                Displacement method
                <select value={displacementMethod} onChange={(event) => setDisplacementMethod(event.target.value as 'dft' | 'elastix' | 'optical_flow' | 'elastix3d')}>
                  <option value="dft">DFT</option>
                  <option value="elastix">Elastix</option>
                  <option value="optical_flow">Optical Flow</option>
                  <option value="elastix3d">Elastix 3D</option>
                </select>
              </label>

              <label style={{ display: 'grid', gap: '6px' }}>
                Display mode
                <select value={plotMode} onChange={(event) => setPlotMode(event.target.value as 'magnitude' | 'field' | 'both')}>
                  <option value="magnitude">Magnitude</option>
                  <option value="field">Field</option>
                  <option value="both">Both</option>
                </select>
              </label>

              <label style={{ display: 'grid', gap: '6px' }}>
                Optical Flow radius
                <input type="number" min={1} step={1} value={opticalFlowRadius} onChange={(event) => setOpticalFlowRadius(Number(event.target.value))} />
              </label>
            </div>
          </section>

          <section style={{ margin: '0 0 16px', padding: '20px', border: '1px solid #ddd', borderRadius: '8px', backgroundColor: '#fff', textAlign: 'left' }}>
            <h3>Step 2b. Plot appearance</h3>
            <p style={{ marginTop: 0, color: '#5b6f86' }}>
              These values are applied to the generated matplotlib plots (displacement and traction) on the next run.
            </p>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '16px' }}>
              <label style={{ display: 'grid', gap: '6px' }}>
                Colormap
                <select value={colormapName} onChange={(event) => setColormapName(event.target.value as 'jet' | 'viridis' | 'inferno' | 'turbo')}>
                  <option value="jet">Jet</option>
                  <option value="viridis">Viridis</option>
                  <option value="inferno">Inferno</option>
                  <option value="turbo">Turbo</option>
                </select>
              </label>

              <label style={{ display: 'grid', gap: '6px' }}>
                Quiver density (stride)
                <input
                  type="number"
                  min={1}
                  max={20}
                  step={1}
                  value={quiverStride}
                  onChange={(event) => setQuiverStride(Math.max(1, Number(event.target.value) || 1))}
                />
              </label>

              <label style={{ display: 'grid', gap: '6px' }}>
                Quiver length scale
                <input
                  type="number"
                  min={0.1}
                  max={10}
                  step={0.1}
                  value={quiverLengthScale}
                  onChange={(event) => setQuiverLengthScale(Math.max(0.1, Number(event.target.value) || 1))}
                />
              </label>

              <label style={{ display: 'grid', gap: '6px' }}>
                Quiver size scale
                <input
                  type="number"
                  min={0.1}
                  max={10}
                  step={0.1}
                  value={quiverSizeScale}
                  onChange={(event) => setQuiverSizeScale(Math.max(0.1, Number(event.target.value) || 1))}
                />
              </label>

              <label style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '22px' }}>
                <input type="checkbox" checked={showScaleBar} onChange={(event) => setShowScaleBar(event.target.checked)} />
                Show scale bar (um)
              </label>
            </div>
          </section>

          {tool.parameters.length > 0 && (
            <section style={{ margin: '0 0 16px', padding: '20px', border: '1px solid #ddd', borderRadius: '8px', backgroundColor: '#fff', textAlign: 'left' }}>
              <h3>Step 3. Analysis parameters</h3>
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

          <section style={{ margin: '0 0 16px', padding: '20px', border: '1px solid #ddd', borderRadius: '8px', backgroundColor: '#fff', textAlign: 'left' }}>
            <h3>Step 4. Optional crop/alignment</h3>
            <label style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
              <input type="checkbox" checked={cropEnabled} onChange={(event) => setCropEnabled(event.target.checked)} />
              Enable crop
            </label>

            <label style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
              <input type="checkbox" checked={rigidAlignCrop} onChange={(event) => setRigidAlignCrop(event.target.checked)} />
              Apply rigid alignment after crop (recommended)
            </label>

            {cropEnabled && (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: '12px' }}>
                <label style={{ display: 'grid', gap: '6px' }}>
                  x0
                  <input type="number" min={0} step={1} value={cropX0} onChange={(event) => setCropX0(Number(event.target.value))} />
                </label>
                <label style={{ display: 'grid', gap: '6px' }}>
                  y0
                  <input type="number" min={0} step={1} value={cropY0} onChange={(event) => setCropY0(Number(event.target.value))} />
                </label>
                <label style={{ display: 'grid', gap: '6px' }}>
                  width
                  <input type="number" min={1} step={1} value={cropW} onChange={(event) => setCropW(Number(event.target.value))} />
                </label>
                <label style={{ display: 'grid', gap: '6px' }}>
                  height
                  <input type="number" min={1} step={1} value={cropH} onChange={(event) => setCropH(Number(event.target.value))} />
                </label>
              </div>
            )}
          </section>

          <section style={{ margin: '0 0 16px', padding: '20px', border: '1px solid #ddd', borderRadius: '8px', backgroundColor: '#fff', textAlign: 'left' }}>
            <h3>Step 5. Run displacement on all frames</h3>
            <p style={{ marginTop: 0, color: '#5b6f86' }}>
              This replicates the Streamlit stage where you first compute displacement, inspect results, then run traction.
            </p>
            <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
              <button
                type="button"
                onClick={() => void runStage('displacement', 'dft')}
                disabled={beforeFileId === null || afterFileId === null || processing}
                style={{ padding: '12px 14px', borderRadius: '6px', border: 'none', background: '#0ea5a4', color: '#fff', cursor: 'pointer' }}
              >
                Run DFT on all frames
              </button>
              <button
                type="button"
                onClick={() => void runStage('displacement', 'elastix')}
                disabled={beforeFileId === null || afterFileId === null || processing}
                style={{ padding: '12px 14px', borderRadius: '6px', border: 'none', background: '#14b8a6', color: '#fff', cursor: 'pointer' }}
              >
                Run Elastix on all frames
              </button>
              <button
                type="button"
                onClick={() => void runStage('displacement', 'optical_flow')}
                disabled={beforeFileId === null || afterFileId === null || processing}
                style={{ padding: '12px 14px', borderRadius: '6px', border: 'none', background: '#06b6d4', color: '#fff', cursor: 'pointer' }}
              >
                Run Optical Flow on all frames
              </button>
              <button
                type="button"
                onClick={() => void runStage('displacement', 'elastix3d')}
                disabled={beforeFileId === null || afterFileId === null || processing}
                style={{ padding: '12px 14px', borderRadius: '6px', border: 'none', background: '#0284c7', color: '#fff', cursor: 'pointer' }}
              >
                Run Elastix for 3D
              </button>
            </div>
            <p style={{ marginBottom: 0, marginTop: '12px', color: '#4b6380' }}>
              Displacement status: {displacementReady ? `ready (${lastDisplacementMethod})` : 'not computed yet'}
            </p>
          </section>

          <section style={{ margin: '0 0 16px', padding: '20px', border: '1px solid #ddd', borderRadius: '8px', backgroundColor: '#fff', textAlign: 'left' }}>
            <h3>Step 6. Run traction force on all frames</h3>
            <p style={{ marginTop: 0, color: '#5b6f86' }}>
              This uses your current displacement setup and physical parameters.
            </p>
            <button
              type="button"
              onClick={() => void runStage('traction')}
              disabled={!displacementReady || processing}
              style={{ padding: '12px 16px', borderRadius: '6px', border: 'none', background: '#16a34a', color: '#fff', cursor: displacementReady && !processing ? 'pointer' : 'not-allowed' }}
            >
              Run Traction Force on all frames
            </button>
            <p style={{ marginBottom: 0, marginTop: '12px', color: '#4b6380' }}>
              Traction status: {tractionReady ? 'ready' : 'not computed yet'}
            </p>
          </section>

          <section style={{ margin: '0 0 16px', padding: '20px', border: '1px solid #ddd', borderRadius: '8px', backgroundColor: '#fff', textAlign: 'left' }}>
            <h3>Step 7. Download and reset</h3>
            <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
              <button
                type="button"
                onClick={handleDownload}
                disabled={!downloadReady}
                style={{ padding: '12px 16px', borderRadius: '6px', border: 'none', background: downloadReady ? '#2563eb' : '#94a3b8', color: '#fff' }}
              >
                Download results (ZIP)
              </button>
              <button
                type="button"
                onClick={clearAllData}
                style={{ padding: '12px 16px', borderRadius: '6px', border: '1px solid #cbd5e1', background: '#fff', color: '#1e293b' }}
              >
                Clear all data (manual reset)
              </button>
            </div>
          </section>

          <section style={{ margin: '0', padding: '20px', border: '1px solid #ddd', borderRadius: '8px', backgroundColor: '#fff', textAlign: 'left' }}>
            <h3>Help</h3>
            <ul style={{ marginTop: '8px', color: '#4b6380' }}>
              <li>Before Image: moving/timelapse TIFF stack.</li>
              <li>After Image: static reference TIFF stack.</li>
              <li>Half Window Size: larger is more robust, smaller is more detailed.</li>
              <li>Step Size: smaller is higher resolution, but slower.</li>
              <li>Recommended flow: upload {'=>'} pick dimensionality {'=>'} crop/alignment {'=>'} displacement {'=>'} traction {'=>'} download.</li>
            </ul>
          </section>
        </aside>

        <section className="tfm-viewport">
          <div className="workspace-panels" style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '20px', textAlign: 'left' }}>
            <section style={{ padding: '16px', border: '1px solid #ddd', borderRadius: '8px', backgroundColor: '#fff' }}>
              <h4>Before image</h4>
              <div style={{ display: 'grid', placeItems: 'center', minHeight: '220px' }}>
                {beforeImageUrl ? <img className="workspace-image" src={beforeImageUrl} alt="Before" /> : <span style={{ color: '#999' }}>Before preview</span>}
              </div>
            </section>

            <section style={{ padding: '16px', border: '1px solid #ddd', borderRadius: '8px', backgroundColor: '#fff' }}>
              <h4>After image</h4>
              <div style={{ display: 'grid', placeItems: 'center', minHeight: '220px' }}>
                {afterImageUrl ? <img className="workspace-image" src={afterImageUrl} alt="After" /> : <span style={{ color: '#999' }}>After preview</span>}
              </div>
            </section>

            <section style={{ padding: '16px', border: '1px solid #ddd', borderRadius: '8px', backgroundColor: '#fff' }}>
              <h4>Displacement</h4>
              <div className="workspace-image-stage" style={{ display: 'grid', placeItems: 'center', borderRadius: '8px', minHeight: '220px', overflow: 'visible' }}>
                {displacementPlotUrl && <img className="workspace-image" src={displacementPlotUrl} alt="Displacement plot" />}
                {!displacementPlotUrl && !processing && lastStage === 'displacement' && matplotlibImageUrl && (
                  <img className="workspace-image" src={matplotlibImageUrl} alt="Displacement plot" />
                )}
                {!displacementPlotUrl && !processing && !(lastStage === 'displacement' && matplotlibImageUrl) && <span style={{ color: '#999' }}>Displacement preview</span>}
                {!processing && liveReplotting && <span style={{ color: '#4b6380', fontSize: '12px' }}>Updating plot...</span>}
              </div>
            </section>

            <section style={{ padding: '16px', border: '1px solid #ddd', borderRadius: '8px', backgroundColor: '#fff' }}>
              <h4>Force / Traction</h4>
              <div className="workspace-image-stage" style={{ display: 'grid', placeItems: 'center', borderRadius: '8px', minHeight: '220px', overflow: 'visible' }}>
                {processing && processingStage === 'traction' && (
                  <div aria-label="Processing traction" style={{ width: '48px', height: '48px', border: '5px solid #777', borderTopColor: '#fff', borderRadius: '50%', animation: 'spin 1s linear infinite' }} />
                )}
                {!processing && tractionPlotUrl && <img className="workspace-image" src={tractionPlotUrl} alt="Traction plot" />}
                {!processing && !tractionPlotUrl && lastStage === 'traction' && vectorSlice && (
                  <div style={{ width: '100%', height: '100%', display: 'grid', gridTemplateRows: '1fr auto auto', gap: '8px', padding: '8px' }}>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: '10px', alignItems: 'stretch' }}>
                      <div
                        style={{
                          minHeight: '220px',
                          display: 'grid',
                          placeItems: 'center',
                          background: '#ffffff',
                          border: '1px solid #d7e0ea',
                          borderRadius: '6px',
                          padding: '8px',
                        }}
                      >
                        <canvas
                          ref={vectorCanvasRef}
                          style={{
                            width: '100%',
                            height: 'auto',
                            display: 'block',
                            border: '1px solid #111827',
                            imageRendering: 'pixelated',
                            background: '#ffffff',
                          }}
                        />
                      </div>
                      {(plotMode === 'magnitude' || plotMode === 'both' || lastStage === 'traction') && (
                        <div style={{ width: '34px', display: 'grid', gridTemplateRows: '16px 1fr 16px', gap: '8px', alignItems: 'center' }}>
                          <div style={{ fontSize: '11px', color: '#4b6380', textAlign: 'center' }}>{maxDisplayMagnitude.toFixed(3)}</div>
                          <div style={{ width: '100%', height: '100%', borderRadius: '3px', background: colorbarGradient, border: '1px solid #d3dceb' }} />
                          <div style={{ fontSize: '11px', color: '#4b6380', textAlign: 'center' }}>0</div>
                        </div>
                      )}
                    </div>
                    <div style={{ color: '#4b6380', fontSize: '13px', fontWeight: 600 }}>
                      Force quivers shown from vector field (live preview). Units: {displayUnit}.
                    </div>
                    <div style={{ color: '#4b6380', fontSize: '13px' }}>
                      View mode: {plotMode}. Vector dim: {vectorSlice.vector_dim}. Sample stride: {vectorSlice.stride}.
                    </div>
                  </div>
                )}
                {!processing && !tractionPlotUrl && !(lastStage === 'traction' && vectorSlice) && (
                  <span style={{ color: '#999' }}>Traction preview</span>
                )}
                {!processing && liveReplotting && <span style={{ color: '#4b6380', fontSize: '12px' }}>Updating plot...</span>}
                {!processing && vectorLoading && <span style={{ color: '#4b6380' }}>Loading vector field...</span>}
              </div>
            </section>
          </div>

          <div className="slice-controls" style={{ marginTop: '16px' }}>
            <label htmlFor="slice-slider">Slice {currentSlice + 1} of {sliceCount}</label>
            <input
              id="slice-slider"
              type="range"
              min="0"
              max={Math.max(0, sliceCount - 1)}
              value={currentSlice}
              onChange={(event) => void handleSliceChange(event)}
              disabled={beforeFileId === null || beforeUploading}
            />
          </div>

          <section style={{ marginTop: '16px', padding: '20px', border: '1px solid #ddd', borderRadius: '8px', backgroundColor: '#fff', textAlign: 'left' }}>
            <h3>Inspection status</h3>
            <p style={{ marginTop: 0, color: '#5b6f86' }}>
              Overlay behavior from Streamlit is represented by synchronized before/result views and slice selection.
              Use the slider to move through frames/slices and inspect reconstruction quality.
            </p>
            <p style={{ marginBottom: '8px', color: '#4b6380' }}>
              Last computed stage: {lastStage}
            </p>
            {error && <div style={{ backgroundColor: '#f8d7da', color: '#721c24', padding: '10px', borderRadius: '4px', marginBottom: '10px' }}>{error}</div>}
            {resultSummary && (
              <div style={{ backgroundColor: '#d1e7dd', color: '#0f5132', padding: '10px', borderRadius: '4px', marginBottom: '10px' }}>
                {typeof resultSummary.displacement_frames === 'number' && <span>Displacement frames: {resultSummary.displacement_frames}. </span>}
                {typeof resultSummary.traction_frames === 'number' && <span>Traction frames: {resultSummary.traction_frames}. </span>}
                {typeof resultSummary.duration_seconds === 'number' && <span>Processing time: {resultSummary.duration_seconds}s.</span>}
              </div>
            )}
            <p style={{ marginTop: 0, color: '#333' }}>{statusText}</p>
          </section>
        </section>
      </div>
    </div>
  );
};

export default TractionForceWorkspace;
