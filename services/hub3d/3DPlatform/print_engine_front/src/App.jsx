import { Suspense, useEffect, useMemo, useRef, useState } from "react"
import axios from "axios"

import { Canvas, useLoader, useThree } from "@react-three/fiber"
import { OrbitControls } from "@react-three/drei"
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js"
import { ThreeMFLoader } from "three/examples/jsm/loaders/3MFLoader.js"
import * as THREE from "three"

import "./App.css"

const API = import.meta.env.VITE_API_URL || `${window.location.protocol}//${window.location.hostname}:8000`
const DEFAULT_PRINTER_INTERFACE = "http://192.168.1.193/#/home"
const BED_SIZE = 235
const BED_CENTER = BED_SIZE / 2

THREE.Object3D.DEFAULT_UP.set(0, 0, 1)

function fitCamera(camera, controls, object) {
  const box = new THREE.Box3().setFromObject(object)
  if (!Number.isFinite(box.min.x) || !Number.isFinite(box.max.x)) return

  const size = new THREE.Vector3()
  const center = new THREE.Vector3()

  box.getSize(size)
  box.getCenter(center)

  const maxDim = Math.max(size.x, size.y, size.z, 20)
  const dist = maxDim * 1.9

  camera.up.set(0, 0, 1)
  camera.position.set(center.x + dist, center.y - dist, center.z + dist * 0.75)
  camera.lookAt(center)
  camera.updateProjectionMatrix()

  if (controls?.current) {
    controls.current.target.copy(center)
    controls.current.update()
  }
}

function BedGrid() {
  return (
    <group>
      <gridHelper
        args={[BED_SIZE, 22]}
        position={[BED_CENTER, BED_CENTER, 0]}
        rotation={[Math.PI / 2, 0, 0]}
      />
      <axesHelper args={[60]} />
    </group>
  )
}

function STLModel({ url, onDimensions }) {
  const geometry = useLoader(STLLoader, url)
  const meshRef = useRef()
  const controls = useRef()
  const { camera } = useThree()

  const fixedGeometry = useMemo(() => {
    const g = geometry.clone()
    g.computeVertexNormals()
    g.computeBoundingBox()

    const box = g.boundingBox
    if (!box) return g

    const size = new THREE.Vector3()
    box.getSize(size)
    onDimensions?.({ x: size.x, y: size.y, z: size.z })

    const centerX = (box.min.x + box.max.x) / 2
    const centerY = (box.min.y + box.max.y) / 2
    const minZ = box.min.z

    // Correction uniquement pour l'affichage :
    // STL en coordonnées machine Z-up, centré sur le plateau et posé sur Z=0.
    g.translate(BED_CENTER - centerX, BED_CENTER - centerY, -minZ)
    return g
  }, [geometry, onDimensions])

  useEffect(() => {
    if (meshRef.current) fitCamera(camera, controls, meshRef.current)
  }, [camera, fixedGeometry])

  return (
    <>
      <OrbitControls ref={controls} makeDefault />
      <mesh ref={meshRef} geometry={fixedGeometry}>
        <meshStandardMaterial color="#f59e0b" roughness={0.55} metalness={0.05} />
      </mesh>
    </>
  )
}

function ThreeMFModel({ url, onDimensions }) {
  const loaded = useLoader(ThreeMFLoader, url)
  const groupRef = useRef()
  const controls = useRef()
  const { camera } = useThree()

  const object = useMemo(() => loaded.clone(true), [loaded])

  useEffect(() => {
    if (!groupRef.current) return

    // Correction uniquement pour l'affichage :
    // on ne modifie pas le fichier 3MF, seulement la position preview.
    groupRef.current.position.set(0, 0, 0)
    groupRef.current.rotation.set(0, 0, 0)

    const box = new THREE.Box3().setFromObject(groupRef.current)
    if (!Number.isFinite(box.min.x) || !Number.isFinite(box.max.x)) return

    const size = new THREE.Vector3()
    box.getSize(size)
    onDimensions?.({ x: size.x, y: size.y, z: size.z })

    const center = new THREE.Vector3()
    box.getCenter(center)

    groupRef.current.position.x += BED_CENTER - center.x
    groupRef.current.position.y += BED_CENTER - center.y
    groupRef.current.position.z += -box.min.z

    fitCamera(camera, controls, groupRef.current)
  }, [camera, object, onDimensions])

  return (
    <>
      <OrbitControls ref={controls} makeDefault />
      <primitive ref={groupRef} object={object} />
    </>
  )
}

function parseGCode(lines) {
  const paths = {
    print: [],
    support: [],
    travel: [],
  }

  let x = 0
  let y = 0
  let z = 0
  let e = 0
  let relativeE = false
  let currentFeature = "print"

  const number = "(-?(?:\\d+(?:\\.\\d*)?|\\.\\d+))"
  const rx = new RegExp(`X${number}`, "i")
  const ry = new RegExp(`Y${number}`, "i")
  const rz = new RegExp(`Z${number}`, "i")
  const re = new RegExp(`E${number}`, "i")

  const setFeatureFromComment = (comment) => {
    const upper = comment.trim().toUpperCase()

    // Orca / Bambu / Prusa / Cura styles:
    // ; FEATURE: Inner wall
    // ; FEATURE: Support
    // ; TYPE:WALL-INNER
    // Important: only use explicit FEATURE/TYPE markers.
    const featureMatch = upper.match(/(?:FEATURE|TYPE)\s*:\s*([^;]+)/)
    if (!featureMatch) return

    const role = featureMatch[1].trim()

    if (
      role.includes("TRAVEL") ||
      role.includes("WIPE") ||
      role.includes("RETRACT") ||
      role.includes("RETRACTION") ||
      role.includes("UNRETRACT") ||
      role.includes("CUSTOM") ||
      role.includes("SEAM")
    ) {
      currentFeature = "travel"
      return
    }

    if (role.includes("SUPPORT")) {
      currentFeature = "support"
      return
    }

    // Any other typed extrusion is part of the model:
    // wall, infill, bridge, top/bottom surface, gap fill, overhang, skirt/brim, etc.
    currentFeature = "print"
  }

  for (const raw of lines) {
    const trimmed = raw.trim()
    if (!trimmed) continue

    const commentIndex = trimmed.indexOf(";")
    const command = (commentIndex >= 0 ? trimmed.slice(0, commentIndex) : trimmed).trim()
    const comment = commentIndex >= 0 ? trimmed.slice(commentIndex + 1).trim() : ""

    if (comment) setFeatureFromComment(comment)
    if (!command) continue

    const upperCmd = command.toUpperCase()

    if (upperCmd.startsWith("M82")) {
      relativeE = false
      continue
    }

    if (upperCmd.startsWith("M83")) {
      relativeE = true
      continue
    }

    if (upperCmd.startsWith("G92")) {
      const eMatch = command.match(re)
      if (eMatch) e = parseFloat(eMatch[1])
      continue
    }

    if (!upperCmd.startsWith("G0") && !upperCmd.startsWith("G1") && !upperCmd.startsWith("G2") && !upperCmd.startsWith("G3")) continue

    const xMatch = command.match(rx)
    const yMatch = command.match(ry)
    const zMatch = command.match(rz)
    const eMatch = command.match(re)

    const nx = xMatch ? parseFloat(xMatch[1]) : x
    const ny = yMatch ? parseFloat(yMatch[1]) : y
    const nz = zMatch ? parseFloat(zMatch[1]) : z

    const dx = nx - x
    const dy = ny - y
    const dz = nz - z
    const hasMove = Math.abs(dx) > 1e-9 || Math.abs(dy) > 1e-9 || Math.abs(dz) > 1e-9
    const hasXYMove = Math.abs(dx) > 1e-9 || Math.abs(dy) > 1e-9

    let hasMaterial = false

    if (eMatch) {
      const ev = parseFloat(eMatch[1])

      // This is the robust rule for preview:
      // If there is an XY move and an E value while current feature is not travel/retract,
      // draw it as deposited material. Some Orca/Klipper relative G-code can make the
      // absolute E comparison unreliable for preview, while Orca still classifies it by feature.
      if (hasXYMove && currentFeature !== "travel") {
        if (relativeE) {
          hasMaterial = Math.abs(ev) > 1e-9
          e += ev
        } else {
          hasMaterial = Math.abs(ev - e) > 1e-9
          e = ev
        }
      } else {
        if (relativeE) e += ev
        else e = ev
      }
    }

    if (hasMove) {
      if (hasMaterial) {
        const key = currentFeature === "support" ? "support" : "print"
        paths[key].push(x, y, z, nx, ny, nz)
      } else {
        // Kept for optional debug only; not rendered by default.
        paths.travel.push(x, y, z, nx, ny, nz)
      }
    }

    x = nx
    y = ny
    z = nz
  }

  const visible = [...paths.print, ...paths.support]
  let dimensions = null

  if (visible.length >= 3) {
    let minX = Infinity, minY = Infinity, minZ = Infinity
    let maxX = -Infinity, maxY = -Infinity, maxZ = -Infinity

    for (let i = 0; i < visible.length; i += 3) {
      const px = visible[i]
      const py = visible[i + 1]
      const pz = visible[i + 2]

      minX = Math.min(minX, px)
      minY = Math.min(minY, py)
      minZ = Math.min(minZ, pz)
      maxX = Math.max(maxX, px)
      maxY = Math.max(maxY, py)
      maxZ = Math.max(maxZ, pz)
    }

    dimensions = {
      x: maxX - minX,
      y: maxY - minY,
      z: maxZ - minZ,
    }
  }

  return { paths, dimensions }
}

function LinePath({ points, color, opacity = 1 }) {
  const geometry = useMemo(() => {
    const g = new THREE.BufferGeometry()
    g.setAttribute("position", new THREE.Float32BufferAttribute(points, 3))
    return g
  }, [points])

  if (!points.length) return null

  return (
    <lineSegments geometry={geometry}>
      <lineBasicMaterial color={color} transparent={opacity < 1} opacity={opacity} />
    </lineSegments>
  )
}

function GCodeModel({ lines, onDimensions }) {
  const groupRef = useRef()
  const controls = useRef()
  const { camera } = useThree()
  const parsed = useMemo(() => parseGCode(lines), [lines])
  const paths = parsed.paths

  useEffect(() => {
    if (parsed.dimensions) onDimensions?.(parsed.dimensions)
    if (groupRef.current) fitCamera(camera, controls, groupRef.current)
  }, [camera, parsed, onDimensions])

  return (
    <>
      <OrbitControls ref={controls} makeDefault />
      <group ref={groupRef}>
        {/* Déplacements volontairement masqués : ils saturent la preview et ne représentent pas du matériau déposé */}
        <LinePath points={paths.print} color="#f59e0b" />
        <LinePath points={paths.support} color="#22c55e" />
      </group>
    </>
  )
}

function PrintScene({ stlUrl, projectUrl, gcodeLines, onDimensions }) {
  return (
    <Canvas
      camera={{ position: [260, -260, 180], fov: 45, up: [0, 0, 1] }}
      gl={{ antialias: true }}
    >
      <color attach="background" args={["#0f172a"]} />
      <ambientLight intensity={0.85} />
      <directionalLight position={[120, -120, 180]} intensity={1.15} />
      <BedGrid />

      <Suspense fallback={null}>
        {gcodeLines ? (
          <GCodeModel lines={gcodeLines} onDimensions={onDimensions} />
        ) : projectUrl ? (
          <ThreeMFModel url={projectUrl} onDimensions={onDimensions} />
        ) : stlUrl ? (
          <STLModel url={stlUrl} onDimensions={onDimensions} />
        ) : null}
      </Suspense>
    </Canvas>
  )
}

export default function App() {
  const [file, setFile] = useState(null)
  const [jobId, setJobId] = useState(null)

  const [printer, setPrinter] = useState("ender3v3ke")
  const [filament, setFilament] = useState("pla")

  const [scale, setScale] = useState(1)
  const [quantity, setQuantity] = useState(1)
  const [supportType, setSupportType] = useState("off")
  const [supportThreshold, setSupportThreshold] = useState(45)
  const [supportBedOnly, setSupportBedOnly] = useState(false)
  const [infill, setInfill] = useState(15)
  const [infillPattern, setInfillPattern] = useState("gyroid")
  const [brim, setBrim] = useState(5)
  const [layer, setLayer] = useState(0.2)
  const [wallLoops, setWallLoops] = useState(2)

  const [status, setStatus] = useState("idle")
  const [message, setMessage] = useState("")
  const [printerStatus, setPrinterStatus] = useState("unknown")
  const [printerMessage, setPrinterMessage] = useState("")
  const [printerFile, setPrinterFile] = useState(null)
  const [printerLive, setPrinterLive] = useState(null)
  const [printerInterfaceUrl, setPrinterInterfaceUrl] = useState(DEFAULT_PRINTER_INTERFACE)

  const [stlUrl, setStlUrl] = useState(null)
  const [projectUrl, setProjectUrl] = useState(null)
  const [gcodeLines, setGcodeLines] = useState(null)
  const [gcodeUrl, setGcodeUrl] = useState(null)
  const [modelDimensions, setModelDimensions] = useState(null)

  const absoluteUrl = (path) => {
    if (!path) return null
    if (path.startsWith("http")) return path
    return `${API}${path}`
  }


  const formatDuration = (seconds) => {
    if (seconds === null || seconds === undefined || Number.isNaN(Number(seconds))) return "--"
    const total = Math.max(0, Math.round(Number(seconds)))
    const h = Math.floor(total / 3600)
    const m = Math.floor((total % 3600) / 60)
    const s = total % 60
    if (h > 0) return `${h}h ${String(m).padStart(2, "0")}m`
    if (m > 0) return `${m}m ${String(s).padStart(2, "0")}s`
    return `${s}s`
  }

  const refreshPrinterStatus = async () => {
    try {
      const res = await axios.get(`${API}/printer/live-status`)
      const live = res.data
      setPrinterLive(live)
      setPrinterStatus(live.state_label || live.state || "online")
      setPrinterMessage(live.message || (live.online ? "Imprimante connectée" : "Moonraker indisponible"))
      if (live.interface_url) setPrinterInterfaceUrl(live.interface_url)
      if (live.filename) setPrinterFile(live.filename)
    } catch (err) {
      console.error(err)
      setPrinterLive({ online: false, state: "offline", progress: 0 })
      setPrinterStatus("Hors ligne")
      setPrinterMessage("Moonraker indisponible")
    }
  }

  useEffect(() => {
    axios.get(`${API}/printer/config`)
      .then((res) => {
        if (res.data.interface_url) setPrinterInterfaceUrl(res.data.interface_url)
      })
      .catch(() => {})

    refreshPrinterStatus()
    const timer = setInterval(refreshPrinterStatus, 3000)
    return () => clearInterval(timer)
  }, [])

  const handleFile = async (e) => {
    const selected = e.target.files[0]
    if (!selected) return

    setFile(selected)
    setStatus("uploading")
    setMessage("Upload STL en cours...")
    setProjectUrl(null)
    setGcodeLines(null)
    setGcodeUrl(null)
    setStlUrl(URL.createObjectURL(selected))
    setModelDimensions(null)

    const formData = new FormData()
    formData.append("file", selected)

    try {
      const res = await axios.post(`${API}/upload-stl`, formData)
      setJobId(res.data.job_id)
      setStatus("uploaded")
      setMessage("STL chargé. Régle les paramètres puis génère le 3MF.")
    } catch (err) {
      console.error(err)
      setStatus("error")
      setMessage("Erreur upload STL")
    }
  }

  const handleGenerate3MF = async () => {
    if (!jobId) return

    setStatus("generating_3mf")
    setMessage(`Génération 3MF avec template ${printer.toUpperCase()} / ${filament.toUpperCase()}...`)
    setProjectUrl(null)
    setGcodeLines(null)
    setGcodeUrl(null)
    setModelDimensions(null)

    const formData = new FormData()
    formData.append("job_id", jobId)
    formData.append("printer", printer)
    formData.append("filament", filament)
    formData.append("scale", String(scale))
    formData.append("quantity", String(quantity))
    formData.append("support_type", supportType)
    formData.append("support_threshold", String(supportThreshold))
    formData.append("support_bed_only", String(supportBedOnly))
    formData.append("infill", String(infill))
    formData.append("infill_pattern", infillPattern)
    formData.append("brim", String(brim))
    formData.append("layer", String(layer))
    formData.append("wall_loops", String(wallLoops))

    try {
      const res = await axios.post(`${API}/generate-3mf`, formData)
      setProjectUrl(absoluteUrl(res.data.project_url))
      setStatus(res.data.status)
      setMessage("3MF fusionné prêt. Vérifie le modèle puis lance le slicing.")
    } catch (err) {
      console.error(err)
      setStatus("error")
      setMessage(err.response?.data?.error || err.response?.data?.status || "Erreur génération 3MF")
    }
  }

  const handleSlice = async () => {
    if (!jobId) return

    setStatus("slicing")
    setMessage("Slicing Orca CLI en cours...")
    setGcodeLines(null)
    setGcodeUrl(null)
    setModelDimensions(null)

    const formData = new FormData()
    formData.append("job_id", jobId)

    try {
      const res = await axios.post(`${API}/slice`, formData)
      const url = absoluteUrl(res.data.gcode_url)
      const gcodeRes = await fetch(url)
      const text = await gcodeRes.text()

      setGcodeUrl(url)
      setGcodeLines(text.split("\n"))
      setStatus(res.data.status)
      setMessage("G-code généré.")
    } catch (err) {
      console.error(err)
      setStatus("error")
      setMessage(err.response?.data?.error || err.response?.data?.status || "Erreur slicing")
    }
  }


  const handleSendToPrinter = async () => {
    if (!jobId) return

    setStatus("uploading_to_printer")
    setMessage("Envoi du G-code vers l'imprimante...")

    const formData = new FormData()
    formData.append("job_id", jobId)

    try {
      const res = await axios.post(`${API}/printer/upload-gcode`, formData)
      setPrinterFile(res.data.filename)
      setStatus(res.data.status)
      setMessage(`G-code envoyé à l'imprimante : ${res.data.filename}`)
      refreshPrinterStatus()
    } catch (err) {
      console.error(err)
      setStatus("error")
      setMessage(err.response?.data?.error || err.response?.data?.status || "Erreur envoi imprimante")
    }
  }

  const handleStartPrinter = async () => {
    if (!printerFile) return

    const formData = new FormData()
    formData.append("filename", printerFile)

    try {
      const res = await axios.post(`${API}/printer/start`, formData)
      setStatus(res.data.status)
      setMessage(`Impression lancée : ${printerFile}`)
      refreshPrinterStatus()
    } catch (err) {
      console.error(err)
      setStatus("error")
      setMessage(err.response?.data?.error || err.response?.data?.status || "Erreur lancement impression")
    }
  }

  const handleSendAndStart = async () => {
    if (!jobId) return

    setStatus("uploading_and_starting")
    setMessage("Envoi du G-code puis lancement de l'impression...")

    const formData = new FormData()
    formData.append("job_id", jobId)

    try {
      const res = await axios.post(`${API}/printer/upload-and-start`, formData)
      setPrinterFile(res.data.filename)
      setStatus(res.data.status)
      setMessage(`G-code envoyé et impression lancée : ${res.data.filename}`)
      refreshPrinterStatus()
    } catch (err) {
      console.error(err)
      setStatus("error")
      setMessage(err.response?.data?.error || err.response?.data?.status || "Erreur envoi/lancement impression")
    }
  }

  const viewerMode = gcodeLines ? "GCODE" : projectUrl ? "3MF" : stlUrl ? "STL" : "EMPTY"

  const formatDim = (v) => Number.isFinite(v) ? v.toFixed(1) : "--"

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <span className="dot" />
          <div>
            <h1>PRINT ENGINE</h1>
            <p>STL → 3MF Orca → G-code</p>
          </div>
        </div>

        <div className="card">
          <label className="label">1. Import STL</label>
          <input type="file" accept=".stl" onChange={handleFile} />
          {file && <div className="file-name">{file.name}</div>}
        </div>

        <div className="card grid">
          <label>
            Imprimante
            <select value={printer} onChange={(e) => setPrinter(e.target.value)}>
              <option value="ender3v3ke">Creality Ender 3 V3 KE</option>
            </select>
          </label>

          <label>
            Filament
            <select value={filament} onChange={(e) => setFilament(e.target.value)}>
              <option value="pla">PLA</option>
              <option value="tpu60">TPU 60A</option>
              <option value="tpu90">TPU 95A</option>
              <option value="abs">ABS</option>
              <option value="petg">PETG</option>       
            </select>
          </label>
        </div>

        <div className="card grid">
          <label>
            Scale
            <input type="number" step="0.01" min="0.01" value={scale} onChange={(e) => setScale(Number(e.target.value))} />
          </label>

          <label>
            Layer
            <select value={layer} onChange={(e) => setLayer(Number(e.target.value))}>
              <option value={0.12}>0.12 qualité</option>
              <option value={0.2}>0.20 standard</option>
              <option value={0.28}>0.28 rapide</option>
            </select>
          </label>

          <label>
            Quantité
            <input type="number" min="1" max="20" value={quantity} onChange={(e) => setQuantity(Math.max(1, Number(e.target.value) || 1))} />
          </label>

          <label>
            Infill %
            <input type="number" min="0" max="100" value={infill} onChange={(e) => setInfill(Number(e.target.value))} />
          </label>

          <label>
            Infill pattern
            <select value={infillPattern} onChange={(e) => setInfillPattern(e.target.value)}>
              <option value="gyroid">Gyroid</option>
              <option value="grid">Grid</option>
              <option value="crosshatch">Crosshatch</option>
              <option value="rectilinear">Rectilinear</option>
            </select>
          </label>

          <label>
            Supports
            <select value={supportType} onChange={(e) => setSupportType(e.target.value)}>
              <option value="off">Off</option>
              <option value="normal(auto)">Normal auto</option>
              <option value="tree(auto)">Tree auto</option>
            </select>
          </label>

          <label>
            Angle support
            <input type="number" min="0" max="89" value={supportThreshold} onChange={(e) => setSupportThreshold(Number(e.target.value))} />
          </label>

          <label>
            Brim mm
            <input type="number" step="0.5" min="0" value={brim} onChange={(e) => setBrim(Number(e.target.value))} />
          </label>

          <label>
            Walls
            <input type="number" min="1" max="10" value={wallLoops} onChange={(e) => setWallLoops(Number(e.target.value))} />
          </label>

          <label className="check">
            <input type="checkbox" checked={supportBedOnly} onChange={(e) => setSupportBedOnly(e.target.checked)} />
            Support plateau uniquement
          </label>
        </div>

        <div className="actions-col">
          <button disabled={!jobId || status === "generating_3mf"} onClick={handleGenerate3MF}>
            Générer 3MF
          </button>

          <button disabled={!projectUrl || status === "slicing"} onClick={handleSlice}>
            Slice G-code
          </button>

          {projectUrl && <a className="download" href={projectUrl} download>Télécharger 3MF</a>}
          {gcodeUrl && <a className="download" href={gcodeUrl} download>Télécharger G-code</a>}
        </div>

        <div className="card printer-card">
          <label className="label">Imprimante Ender 3 V3 KE</label>
          <div className={`printer-pill ${printerLive?.online === false ? "offline" : "online"}`}>
            {printerStatus}
          </div>
          <p className="printer-message">{printerMessage || "Aucun message"}</p>

          <div className="progress-wrap">
            <div className="progress-line">
              <span>Progression</span>
              <strong>{printerLive?.progress ?? 0}%</strong>
            </div>
            <div className="progress-bar">
              <div style={{ width: `${Math.min(100, Math.max(0, printerLive?.progress || 0))}%` }} />
            </div>
          </div>

          <div className="printer-metrics">
            <div><span>Fichier</span><strong>{printerLive?.filename || printerFile || "Aucun"}</strong></div>
            <div><span>Écoulé</span><strong>{formatDuration(printerLive?.elapsed_seconds)}</strong></div>
            <div><span>Restant</span><strong>{formatDuration(printerLive?.remaining_seconds)}</strong></div>
            <div><span>Buse</span><strong>{printerLive?.extruder_temp ?? "--"}° / {printerLive?.extruder_target ?? "--"}°</strong></div>
            <div><span>Plateau</span><strong>{printerLive?.bed_temp ?? "--"}° / {printerLive?.bed_target ?? "--"}°</strong></div>
          </div>

          {printerFile && <p className="printer-file">Fichier prêt : {printerFile}</p>}

          <div className="actions-col printer-actions">
            <a className="download" href={printerInterfaceUrl} target="_blank" rel="noreferrer">
              Ouvrir Interface Creality
            </a>
            <button disabled={!gcodeUrl || status === "uploading_to_printer"} onClick={handleSendToPrinter}>
              Envoyer vers imprimante
            </button>
            <button disabled={!printerFile} onClick={handleStartPrinter}>
              Lancer impression
            </button>
            <button disabled={!gcodeUrl || status === "uploading_and_starting"} onClick={handleSendAndStart}>
              Envoyer + lancer
            </button>
            <button type="button" onClick={refreshPrinterStatus}>
              Actualiser statut
            </button>
          </div>
        </div>

        <div className="status">
          <strong>Status:</strong> {status}
          <p>{message}</p>
        </div>
      </aside>

      <main className="viewer-wrap">
        <div className="viewer-header">
          <span>Viewer: {viewerMode}</span>
          <span className="legend">Plateau 235 × 235 mm</span>
          {modelDimensions && (
            <span className="legend">
              Objet: X {formatDim(modelDimensions.x)} mm · Y {formatDim(modelDimensions.y)} mm · Z {formatDim(modelDimensions.z)} mm
            </span>
          )}
          {gcodeLines && <span className="legend">Orange = pièce · Vert = supports</span>}
        </div>

        <div className="viewer">
          {viewerMode === "EMPTY" ? (
            <div className="placeholder">Importe un STL pour commencer</div>
          ) : (
            <PrintScene stlUrl={stlUrl} projectUrl={projectUrl} gcodeLines={gcodeLines} onDimensions={setModelDimensions} />
          )}
        </div>
      </main>
    </div>
  )
}
