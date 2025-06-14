// Universal Scanner Component for Kirana Konnect
// This component provides consistent scanner functionality across all pages

class UniversalScanner {
    constructor() {
        this.currentStream = null;
        this.scannerCodeReader = null;
        this.isInitialized = false;
    }

    // Initialize scanner modal and events
    init() {
        if (this.isInitialized) return;
        
        // Add event listeners for scanner buttons
        document.addEventListener('click', (e) => {
            if (e.target.closest('[data-scanner-trigger]')) {
                const title = e.target.closest('[data-scanner-trigger]').getAttribute('data-scanner-title') || 'Scan Barcode';
                this.openScanner(title);
            }
        });

        this.isInitialized = true;
    }

    // Open scanner with customizable title
    openScanner(title = 'Scan Barcode') {
        const modal = document.getElementById('scanner-modal');
        const titleElement = document.getElementById('scanner-title');
        
        if (!modal || !titleElement) {
            console.error('Scanner modal elements not found');
            return;
        }

        // Set scanner title
        titleElement.textContent = title;
        modal.classList.remove('hidden');
        
        // Initialize camera
        this.initializeCamera();
    }

    // Initialize camera with proper error handling
    initializeCamera() {
        const video = document.getElementById('scanner-video');
        if (!video) {
            console.error('Scanner video element not found');
            return;
        }

        this.updateScannerStatus('Starting camera...', 'bg-blue-500');
        
        if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
            navigator.mediaDevices.getUserMedia({ 
                video: { 
                    facingMode: 'environment',
                    width: { ideal: 1280 },
                    height: { ideal: 720 }
                } 
            })
            .then((stream) => {
                video.srcObject = stream;
                video.play();
                this.currentStream = stream;
                this.updateScannerStatus('Position barcode in frame', 'bg-green-500');
                
                // Initialize barcode scanning if ZXing is available
                if (typeof ZXing !== 'undefined') {
                    this.scannerCodeReader = new ZXing.BrowserMultiFormatReader();
                    this.scannerCodeReader.decodeFromVideoDevice(undefined, video, (result, err) => {
                        if (result) {
                            const barcodeValue = result.text;
                            this.closeScanner();
                            this.handleBarcodeResult(barcodeValue);
                        }
                    });
                }
            })
            .catch((err) => {
                console.error('Camera error:', err);
                this.updateScannerStatus('Camera access denied - Enter manually below', 'bg-red-500');
            });
        } else {
            this.updateScannerStatus('Camera not supported - Enter manually below', 'bg-orange-500');
        }
    }

    // Close scanner and cleanup resources
    closeScanner() {
        const modal = document.getElementById('scanner-modal');
        if (modal) {
            modal.classList.add('hidden');
        }
        
        // Stop camera stream
        if (this.currentStream) {
            this.currentStream.getTracks().forEach(track => track.stop());
            this.currentStream = null;
        }
        
        // Stop barcode reader
        if (this.scannerCodeReader) {
            this.scannerCodeReader.reset();
            this.scannerCodeReader = null;
        }
    }

    // Update scanner status message
    updateScannerStatus(message, colorClass) {
        const statusElement = document.getElementById('scanner-status');
        if (statusElement) {
            statusElement.innerHTML = `<span class="${colorClass} text-white px-3 py-1 rounded-full text-sm">${message}</span>`;
        }
    }

    // Handle barcode scan result (to be overridden by pages)
    handleBarcodeResult(barcode) {
        console.log('Barcode scanned:', barcode);
        
        // Try to call page-specific handler if it exists
        if (typeof window.onBarcodeScanned === 'function') {
            window.onBarcodeScanned(barcode);
        } else {
            // Default behavior - search for product
            this.performBarcodeSearch(barcode);
        }
    }

    // Default barcode search function
    performBarcodeSearch(barcode) {
        // This will be overridden by each page's specific implementation
        console.log('Searching for barcode:', barcode);
        
        // Try to call global search function if available
        if (typeof performBarcodeSearch === 'function') {
            performBarcodeSearch(barcode);
        }
    }

    // Toggle flashlight (placeholder for real implementation)
    toggleFlashlight() {
        console.log('Flashlight toggled');
        // In a real app, this would control the camera flash
    }

    // Manual barcode entry
    openManualEntry() {
        const modal = document.getElementById('manual-barcode-modal');
        const input = document.getElementById('manual-barcode-input');
        
        if (modal && input) {
            modal.classList.remove('hidden');
            input.focus();
        }
    }

    // Close manual barcode entry
    closeManualEntry() {
        const modal = document.getElementById('manual-barcode-modal');
        const input = document.getElementById('manual-barcode-input');
        
        if (modal) {
            modal.classList.add('hidden');
        }
        
        if (input) {
            input.value = '';
        }
    }

    // Process manual barcode entry
    processManualBarcode() {
        const input = document.getElementById('manual-barcode-input');
        if (input && input.value.trim()) {
            const barcode = input.value.trim();
            this.closeManualEntry();
            this.handleBarcodeResult(barcode);
        }
    }
}

// Global scanner instance
window.universalScanner = new UniversalScanner();

// Global functions for backward compatibility
function openScanner(title) {
    window.universalScanner.openScanner(title);
}

function closeScanner() {
    window.universalScanner.closeScanner();
}

function toggleFlashlight() {
    window.universalScanner.toggleFlashlight();
}

function manualBarcodeEntry() {
    window.universalScanner.openManualEntry();
}

function closeManualBarcode() {
    window.universalScanner.closeManualEntry();
}

function processManualBarcode() {
    window.universalScanner.processManualBarcode();
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    window.universalScanner.init();
});