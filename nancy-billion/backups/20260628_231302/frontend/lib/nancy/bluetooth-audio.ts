'use client'

import { useEffect, useState } from 'react'

export interface BluetoothDeviceInfo {
  id: string
  name: string
  connected: boolean
  type: 'audio' | 'video' | 'other'
}

export function useBluetoothAudio() {
  const [devices, setDevices] = useState<BluetoothDeviceInfo[]>([])
  const [connectedDevice, setConnectedDevice] = useState<BluetoothDeviceInfo | null>(null)
  const [isScanning, setIsScanning] = useState(false)

  // Request access to Bluetooth devices
  const requestBluetoothAccess = useCallback(async () => {
    if (!navigator.bluetooth) {
      console.warn('Bluetooth API not available in this browser')
      return false
    }

    try {
      setIsScanning(true)
      
      // Request device with audio capability
      const device = await navigator.bluetooth.requestDevice({
        filters: [{ services: ['audio_source'] }],
        optionalServices: ['battery_service']
      })

      // Connect to the device
      const server = await device.gatt?.connect()
      
      if (server) {
        const deviceInfo: BluetoothDeviceInfo = {
          id: device.id,
          name: device.name,
          connected: device.gatt?.connected ?? false,
          type: 'audio'
        }
        
        setConnectedDevice(deviceInfo)
        // Update devices list
        setDevices(prev => [...prev.filter(d => d.id !== device.id), deviceInfo])
        
        console.log(`Connected to audio device: ${device.name}`)
        return true
      }
    } catch (error) {
      console.error('Failed to connect to Bluetooth device:', error)
      return false
    } finally {
      setIsScanning(false)
    }
    
    return false
  }, [])

  // Scan for nearby Bluetooth audio devices
  const scanForDevices = useCallback(async () => {
    if (!navigator.bluetooth) {
      console.warn('Bluetooth API not available in this browser')
      return
    }

    try {
      setIsScanning(true)
      
      // Get already paired devices
      const pairedDevices = await navigator.bluetooth.getDevices()
      
      // Filter for audio devices
      const audioDevices = pairedDevices
        .filter(device => 
          device.uuids?.some(uuid => 
            uuid.includes('audio_source') || 
            uuid.includes('audio_sink')
          )
        )
        .map(device => ({
          id: device.id,
          name: device.name,
          connected: device.gatt?.connected ?? false,
          type: 'audio' as const
        }))
      
      setDevices(audioDevices)
      
      // Check if any are currently connected
      const connected = audioDevices.find(device => device.connected)
      if (connected) {
        setConnectedDevice(connected)
      }
    } catch (error) {
      console.error('Failed to scan for Bluetooth devices:', error)
    } finally {
      setIsScanning(false)
    }
  }, [])

  // Disconnect from current device
  const disconnectDevice = useCallback(async () => {
    if (!connectedDevice || !navigator.bluetooth) return
    
    try {
      const device = await navigator.bluetooth.getDevice(connectedDevice.id)
      await device.gatt?.disconnect()
      setConnectedDevice(null)
      console.log(`Disconnected from device: ${connectedDevice.name}`)
    } catch (error) {
      console.error('Failed to disconnect from Bluetooth device:', error)
    }
  }, [connectedDevice])

  // Connect to a specific device
  const connectToDevice = useCallback(async (deviceId: string) => {
    if (!navigator.bluetooth) return false
    
    try {
      setIsScanning(true)
      const device = await navigator.bluetooth.getDevice(deviceId)
      const server = await device.gatt?.connect()
      
      if (server) {
        const deviceInfo: BluetoothDeviceInfo = {
          id: device.id,
          name: device.name,
          connected: device.gatt?.connected ?? false,
          type: 'audio'
        }
        
        setConnectedDevice(deviceInfo)
        // Update devices list
        setDevices(prev => 
          prev.map(d => d.id === deviceId ? deviceInfo : d)
        )
        
        console.log(`Connected to device: ${device.name}`)
        return true
      }
    } catch (error) {
      console.error('Failed to connect to Bluetooth device:', error)
      return false
    } finally {
      setIsScanning(false)
    }
    
    return false
  }, [])

  // Initialize - scan for devices on mount
  useEffect(() => {
    scanForDevices()
    
    // Also listen for Bluetooth device changes
    const handleAvailabilityChanged = () => {
      scanForDevices()
    }
    
    if (navigator.bluetooth) {
      navigator.bluetooth.addEventListener('availabilitychanged', handleAvailabilityChanged)
    }
    
    return () => {
      if (navigator.bluetooth) {
        navigator.bluetooth.removeEventListener('availabilitychanged', handleAvailabilityChanged)
      }
    }
  }, [scanForDevices])

  return {
    devices,
    connectedDevice,
    isScanning,
    requestBluetoothAccess,
    scanForDevices,
    disconnectDevice,
    connectToDevice,
    isConnected: !!connectedDevice
  }
}

// Helper function to check if AirPods are connected
export function isAirPodsConnected(deviceName: string): boolean {
  const airPodsPatterns = [
    /airpods/i,
    /air pods/i,
    /airpod/i
  ]
  
  return airPodsPatterns.some(pattern => pattern.test(deviceName))
}