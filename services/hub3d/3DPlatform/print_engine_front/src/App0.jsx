import { useEffect, useMemo, useState } from "react"
import axios from "axios"

import { Canvas } from "@react-three/fiber"
import {
  OrbitControls,
  Line,
  Center
} from "@react-three/drei"

import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js"

import * as THREE from "three"

import "./App.css"

const API = "http://127.0.0.1:8000"

//
// STL VIEWER
//

function STLModel({ file }) {

  const [geometry, setGeometry] = useState(null)

  useEffect(() => {

    if (!file) return

    const reader = new FileReader()

    reader.onload = function (e) {

      const loader = new STLLoader()

      const geo = loader.parse(e.target.result)

      geo.center()

      setGeometry(geo)
    }

    reader.readAsArrayBuffer(file)

  }, [file])

  if (!geometry) return null

  return (
    <Center>
      <mesh geometry={geometry}>
        <meshStandardMaterial
          color="#00d2ff"
          metalness={0.3}
          roughness={0.2}
        />
      </mesh>
    </Center>
  )
}

//
// GCODE VIEWER
//

function GcodeViewer({ points }) {

  const linePoints = useMemo(() => {

    if (!points || points.length < 2) {
      return []
    }

    let minX = Infinity
    let minY = Infinity
    let minZ = Infinity

    let maxX = -Infinity
    let maxY = -Infinity
    let maxZ = -Infinity

    points.forEach(p => {

      minX = Math.min(minX, p[0])
      minY = Math.min(minY, p[1])
      minZ = Math.min(minZ, p[2])

      maxX = Math.max(maxX, p[0])
      maxY = Math.max(maxY, p[1])
      maxZ = Math.max(maxZ, p[2])

    })

    const centerX = (minX + maxX) / 2
    const centerY = (minY + maxY) / 2
    const centerZ = (minZ + maxZ) / 2

    return points.map(p => [
      p[0] - centerX,
      p[2] - centerZ,
      -(p[1] - centerY)
    ])

  }, [points])

  if (linePoints.length < 2) {
    return null
  }

  return (
    <Line
      points={linePoints}
      color="orange"
      lineWidth={1}
    />
  )
}

//
// APP
//

export default function App() {

  const [file, setFile] = useState(null)

  const [preset, setPreset] = useState("quality")

  const [job, setJob] = useState(null)

  const [loading, setLoading] = useState(false)

  const [gcodePoints, setGcodePoints] = useState([])

  const [mode, setMode] = useState("stl")
  // stl | gcode

  //
  // UPLOAD
  //

  const handleFile = (e) => {

    const selected = e.target.files[0]

    if (!selected) return

    setFile(selected)

    // switch viewer to STL
    setMode("stl")
  }

  //
  // LOAD GCODE
  //

  const loadGcode = async (jobId) => {

    try {

      const res = await axios.get(
        `${API}/api/gcode-preview/${jobId}`
      )

      setGcodePoints(res.data.points || [])

      // switch viewer to GCODE
      setMode("gcode")

    } catch (err) {

      console.error(err)
    }
  }

  //
  // SLICE
  //

  const uploadAndSlice = async () => {

    if (!file) return

    setLoading(true)

    const form = new FormData()

    form.append("file", file)
    form.append("preset", preset)

    try {

      const res = await axios.post(
        `${API}/api/print`,
        form
      )

      setJob(res.data)

      await loadGcode(res.data.job_id)

    } catch (err) {

      console.error(err)

    } finally {

      setLoading(false)
    }
  }

  return (

    <div className="app">

      {/* SIDEBAR */}

      <div className="sidebar">

        <h1>PRINT ENGINE</h1>

        <p>iPad 3D Printing Hub</p>

        <input
          type="file"
          accept=".stl"
          onChange={handleFile}
        />

        <select
          value={preset}
          onChange={(e) => setPreset(e.target.value)}
        >
          <option value="fast">FAST</option>
          <option value="quality">QUALITY</option>
          <option value="strong">STRONG</option>
        </select>

        <button onClick={uploadAndSlice}>
          {loading ? "SLICING..." : "SLICE MODEL"}
        </button>

        {job && (
          <div className="job">

            <p>
              STATUS:
              {" "}
              {job.status}
            </p>

            <p>
              PRESET:
              {" "}
              {job.preset}
            </p>

            <p>
              VIEW:
              {" "}
              {mode.toUpperCase()}
            </p>

          </div>
        )}

      </div>

      {/* VIEWER */}

      <div className="viewer">

        <Canvas camera={{ position: [120, 120, 120] }}>

          <ambientLight intensity={1} />

          <directionalLight
            position={[50, 50, 50]}
            intensity={2}
          />

          <gridHelper args={[300, 30]} />

          <axesHelper args={[100]} />

          <OrbitControls />

          {/* STL MODE */}

          {mode === "stl" && file && (
            <STLModel file={file} />
          )}

          {/* GCODE MODE */}

          {mode === "gcode" && (
            <GcodeViewer points={gcodePoints} />
          )}

        </Canvas>

      </div>

    </div>
  )
}