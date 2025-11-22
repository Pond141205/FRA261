// Global variables
let overviewData = {};
let allSilosData = [];

// API Base URL
const API_BASE = window.location.origin;

// Utility functions
function showLoading() {
    document.getElementById('loadingOverlay').style.display = 'flex';
}

function hideLoading() {
    document.getElementById('loadingOverlay').style.display = 'none';
}

function showToast(message, type = 'success') {
    const toast = document.createElement('div');
    toast.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 1rem 1.5rem;
        background: ${type === 'success' ? '#10B981' : '#EF4444'};
        color: white;
        border-radius: 8px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        z-index: 10000;
        transform: translateX(100%);
        transition: transform 0.3s ease;
    `;
    toast.textContent = message;
    document.body.appendChild(toast);

    setTimeout(() => toast.style.transform = 'translateX(0)', 100);
    setTimeout(() => {
        toast.style.transform = 'translateX(100%)';
        setTimeout(() => document.body.removeChild(toast), 300);
    }, 3000);
}

// API Functions - ใช้ฟังก์ชันเดียวกับ admin dashboard
async function fetchOverviewData() {
    try {
        console.log('🔄 Fetching overview data from API...');
        const response = await fetch('/api/volume_data');
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        console.log('📊 Overview API response:', data);
        
        if (!Array.isArray(data)) {
            throw new Error('Invalid data format from volume_data');
        }
        
        return processOverviewData(data);
        
    } catch (error) {
        console.error('❌ Error fetching overview data:', error);
        return getDemoOverviewData();
    }
}

// ฟังก์ชันประมวลผลข้อมูลจาก volume_data - เหมือนกับใน admin
function processOverviewData(data) {
    console.log('🔄 Processing volume data for overview:', data);
    
    const branchesMap = {};
    let totalSilos = 0;
    let totalCapacity = 0;
    let totalUsed = 0;
    let totalLowCapacity = 0;

    if (Array.isArray(data)) {
        data.forEach((silo, index) => {
            const province = silo.province || 'ไม่ทราบจังหวัด';
            
            // ข้ามถ้า province เป็นค่าว่างหรือถูก soft delete
            if (!province || province.includes('deleted')) {
                return;
            }
            
            if (!branchesMap[province]) {
                branchesMap[province] = {
                    name: province,
                    siloCount: 0,
                    totalCapacity: 0,
                    totalUsed: 0,
                    lowCapacityCount: 0
                };
            }
            
            const siloCapacity = silo.capacity || 1000;
            const currentAmount = silo.volume || 0;
            const percentage = (currentAmount / siloCapacity) * 100;
            const isLowCapacity = percentage < 35;
            
            branchesMap[province].siloCount++;
            branchesMap[province].totalCapacity += siloCapacity;
            branchesMap[province].totalUsed += currentAmount;
            
            if (isLowCapacity) {
                branchesMap[province].lowCapacityCount++;
                totalLowCapacity++;
            }
            
            totalSilos++;
            totalCapacity += siloCapacity;
            totalUsed += currentAmount;
        });
    } else {
        console.warn('⚠️ Data is not an array, using demo data');
        return getDemoOverviewData();
    }

    // Calculate percentages
    Object.values(branchesMap).forEach(branch => {
        if (branch.totalCapacity > 0) {
            branch.usagePercentage = Math.round((branch.totalUsed / branch.totalCapacity) * 100);
        } else {
            branch.usagePercentage = 0;
        }
    });

    const totalUsagePercentage = totalCapacity > 0 ? Math.round((totalUsed / totalCapacity) * 100) : 0;

    console.log('✅ Processed overview data:', {
        branches: branchesMap,
        summary: {
            totalBranches: Object.keys(branchesMap).length,
            totalSilos: totalSilos,
            totalUsagePercentage: totalUsagePercentage,
            totalLowCapacity: totalLowCapacity,
            totalCapacity: totalCapacity,
            totalUsed: totalUsed
        }
    });

    return {
        branches: branchesMap,
        summary: {
            totalBranches: Object.keys(branchesMap).length,
            totalSilos: totalSilos,
            totalUsagePercentage: totalUsagePercentage,
            totalLowCapacity: totalLowCapacity,
            totalCapacity: totalCapacity,
            totalUsed: totalUsed
        }
    };
}

// ฟังก์ชันดึงข้อมูลไซโลทั้งหมด - เหมือนกับใน admin
async function fetchAllSilos() {
    try {
        console.log('🔄 Fetching all silos data...');
        const response = await fetch('/api/volume_data');
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        console.log('📋 All silos data response:', data);
        
        if (!Array.isArray(data)) {
            throw new Error('Invalid data format from volume_data');
        }
        
        return data;
        
    } catch (error) {
        console.error('❌ Error fetching all silos:', error);
        return getDemoSilosData();
    }
}

// ข้อมูลตัวอย่าง - อัพเดทให้เหมือนกับ admin
function getDemoOverviewData() {
    return {
        branches: {
            'สระบุรี': { 
                name: 'สระบุรี', 
                siloCount: 3, 
                totalCapacity: 3000, 
                totalUsed: 1500, 
                lowCapacityCount: 1, 
                usagePercentage: 50 
            },
            'ราชบุรี': { 
                name: 'ราชบุรี', 
                siloCount: 2, 
                totalCapacity: 2000, 
                totalUsed: 1200, 
                lowCapacityCount: 0, 
                usagePercentage: 60 
            },
            'นครราชสีมา': { 
                name: 'นครราชสีมา', 
                siloCount: 2, 
                totalCapacity: 2000, 
                totalUsed: 800, 
                lowCapacityCount: 1, 
                usagePercentage: 40 
            }
        },
        summary: {
            totalBranches: 3,
            totalSilos: 7,
            totalUsagePercentage: 50,
            totalLowCapacity: 2,
            totalCapacity: 7000,
            totalUsed: 3500
        }
    };
}

function getDemoSilosData() {
    return [
        {
            device_id: 'DEV001',
            volume: 500,
            plant_type: 'ข้าวสาร',
            province: 'สระบุรี',
            site_code: 'SB001',
            silo_no: '1',
            capacity: 1000,
            volume_percentage: 50
        },
        {
            device_id: 'DEV002',
            volume: 750,
            plant_type: 'ข้าวโพด',
            province: 'สระบุรี',
            site_code: 'SB001',
            silo_no: '2',
            capacity: 1000,
            volume_percentage: 75
        },
        {
            device_id: 'DEV003',
            volume: 250,
            plant_type: 'ข้าวสาร',
            province: 'สระบุรี',
            site_code: 'SB002',
            silo_no: '1',
            capacity: 1000,
            volume_percentage: 25
        },
        {
            device_id: 'DEV004',
            volume: 600,
            plant_type: 'ข้าวสาร',
            province: 'ราชบุรี',
            site_code: 'RB001',
            silo_no: '1',
            capacity: 1000,
            volume_percentage: 60
        },
        {
            device_id: 'DEV005',
            volume: 600,
            plant_type: 'ข้าวโพด',
            province: 'ราชบุรี',
            site_code: 'RB001',
            silo_no: '2',
            capacity: 1000,
            volume_percentage: 60
        },
        {
            device_id: 'DEV006',
            volume: 400,
            plant_type: 'ข้าวสาร',
            province: 'นครราชสีมา',
            site_code: 'NK001',
            silo_no: '1',
            capacity: 1000,
            volume_percentage: 40
        },
        {
            device_id: 'DEV007',
            volume: 400,
            plant_type: 'ข้าวโพด',
            province: 'นครราชสีมา',
            site_code: 'NK001',
            silo_no: '2',
            capacity: 1000,
            volume_percentage: 40
        }
    ];
}

// UI Functions
function updateSummaryCards(data) {
    const summary = data.summary;
    
    document.getElementById('total-branches').textContent = summary.totalBranches || 0;
    document.getElementById('total-silos').textContent = summary.totalSilos || 0;
    document.getElementById('total-capacity-used').textContent = (summary.totalUsagePercentage || 0) + '%';
    document.getElementById('total-low-capacity').textContent = summary.totalLowCapacity || 0;
    
    // อัพเดทจำนวนไซโลทั้งหมดใน header
    document.getElementById('total-silos-count').textContent = summary.totalSilos || 0;
    
    // ซ่อนการ์ดแจ้งเตือนถ้าไม่มีไซโลปริมาณต่ำ
    const alertCard = document.getElementById('total-alert-card');
    if (summary.totalLowCapacity > 0) {
        alertCard.style.display = 'block';
    } else {
        alertCard.style.display = 'none';
    }
}

function renderBranchesTable(branches) {
    const container = document.getElementById('branches-table-body');
    
    let html = '';
    
    // ตรวจสอบว่า branches มีข้อมูลหรือไม่
    if (!branches || Object.keys(branches).length === 0) {
        html = `
            <tr>
                <td colspan="7" style="text-align: center; padding: 2rem; color: var(--dark);">
                    <i class="fas fa-inbox" style="font-size: 2rem; margin-bottom: 1rem; opacity: 0.5;"></i>
                    <div>ไม่มีข้อมูลสาขา</div>
                </td>
            </tr>
        `;
    } else {
        Object.values(branches).forEach(branch => {
            // ตรวจสอบค่าให้แน่ใจว่าไม่เป็น undefined
            const name = branch.name || 'ไม่ทราบสาขา';
            const siloCount = branch.siloCount || 0;
            const totalCapacity = branch.totalCapacity || 0;
            const totalUsed = branch.totalUsed || 0;
            const usagePercentage = branch.usagePercentage || 0;
            const lowCapacityCount = branch.lowCapacityCount || 0;
            
            const hasAlert = lowCapacityCount > 0;
            const status = hasAlert ? 'มีแจ้งเตือน' : 'ปกติ';
            
            html += `
                <tr class="${hasAlert ? 'alert-row' : ''}">
                    <td>
                        <strong>${name}</strong>
                        ${hasAlert ? '<span class="alert-badge">⚠️</span>' : ''}
                    </td>
                    <td>${siloCount}</td>
                    <td>${totalCapacity.toLocaleString()} ตัน</td>
                    <td>${totalUsed.toLocaleString()} ตัน</td>
                    <td>
                        <div class="progress-bar">
                            <div class="progress-fill" style="width: ${usagePercentage}%"></div>
                        </div>
                        ${usagePercentage}%
                    </td>
                    <td>
                        ${lowCapacityCount > 0 ? 
                            `<span style="color: var(--danger); font-weight: 600;">${lowCapacityCount} ไซโล</span>` : 
                            '<span style="color: var(--success);">0 ไซโล</span>'
                        }
                    </td>
                    <td>
                        <span class="status-indicator ${hasAlert ? 'status-critical' : 'status-normal'}">
                            ${hasAlert ? '<i class="fas fa-exclamation-circle"></i>' : '<i class="fas fa-check-circle"></i>'}
                            ${status}
                        </span>
                    </td>
                </tr>
            `;
        });
    }
    
    container.innerHTML = html;
}

function renderAllSilosTable(silos) {
    const container = document.getElementById('all-silos-table-body');
    
    let html = '';
    
    if (!silos || silos.length === 0) {
        html = `
            <tr>
                <td colspan="9" style="text-align: center; padding: 2rem; color: var(--dark);">
                    <i class="fas fa-inbox" style="font-size: 2rem; margin-bottom: 1rem; opacity: 0.5;"></i>
                    <div>ไม่มีข้อมูลไซโล</div>
                </td>
            </tr>
        `;
    } else {
        // Colors for silos - ใช้สีเดียวกันกับ admin
        const colors = ['#F97316', '#0EA5E9', '#10B981', '#8B5CF6', '#F59E0B', '#EF4444', '#84CC16'];
        const colorMap = new Map();
        
        silos.forEach((silo, index) => {
            const siloName = `ไซโล ${silo.silo_no}`;
            if (!colorMap.has(siloName)) {
                const colorIndex = colorMap.size % colors.length;
                colorMap.set(siloName, colors[colorIndex]);
            }
            const color = colorMap.get(siloName);
            
            const percentage = silo.volume_percentage || Math.round((silo.volume / silo.capacity) * 100);
            const isLowCapacity = percentage < 35;
            const status = isLowCapacity ? 'ปริมาณต่ำ' : 'ปกติ';
            
            html += `
                <tr class="${isLowCapacity ? 'alert-row' : ''}">
                    <td>
                        <span class="silo-color-indicator" style="background: ${color}"></span>
                        <strong>${siloName}</strong>
                    </td>
                    <td>${silo.province || 'ไม่ทราบสาขา'}</td>
                    <td>${silo.plant_type || 'ไม่ทราบประเภท'}</td>
                    <td>${silo.site_code || 'N/A'}</td>
                    <td><code>${silo.device_id}</code></td>
                    <td>${silo.capacity ? silo.capacity.toLocaleString() : '0'} ตัน</td>
                    <td>${silo.volume ? silo.volume.toLocaleString() : '0'} ตัน</td>
                    <td>
                        <div class="progress-bar">
                            <div class="progress-fill" style="width: ${percentage}%"></div>
                        </div>
                        ${percentage}%
                    </td>
                    <td>
                        <span class="status-indicator ${isLowCapacity ? 'status-critical' : 'status-normal'}">
                            ${isLowCapacity ? '<i class="fas fa-exclamation-circle"></i>' : '<i class="fas fa-check-circle"></i>'}
                            ${status}
                        </span>
                    </td>
                </tr>
            `;
        });
    }
    
    container.innerHTML = html;
}

// Refresh functions
async function refreshData() {
    await loadOverviewData();
}

async function refreshSilos() {
    await loadAllSilos();
}

// Initialize data
async function loadOverviewData() {
    showLoading();
    try {
        console.log('🔄 Loading overview data...');
        overviewData = await fetchOverviewData();
        console.log('📊 Overview data loaded:', overviewData);
        
        // ตรวจสอบว่ามีข้อมูลหรือไม่
        if (!overviewData || !overviewData.branches || Object.keys(overviewData.branches).length === 0) {
            throw new Error('No data available');
        }
        
        updateSummaryCards(overviewData);
        renderBranchesTable(overviewData.branches);
        
    } catch (error) {
        console.error('❌ Error loading overview data:', error);
        showToast('เกิดข้อผิดพลาดในการโหลดข้อมูล', 'error');
        
        // แสดงข้อมูล demo เมื่อเกิด error
        const demoData = getDemoOverviewData();
        updateSummaryCards(demoData);
        renderBranchesTable(demoData.branches);
        showToast('กำลังแสดงข้อมูลตัวอย่าง', 'info');
    } finally {
        hideLoading();
    }
}

async function loadAllSilos() {
    showLoading();
    try {
        console.log('🔄 Loading all silos data...');
        allSilosData = await fetchAllSilos();
        console.log('📋 All silos data loaded:', allSilosData);
        
        renderAllSilosTable(allSilosData);
        
    } catch (error) {
        console.error('❌ Error loading all silos:', error);
        showToast('เกิดข้อผิดพลาดในการโหลดข้อมูลไซโล', 'error');
        
        const demoSilos = getDemoSilosData();
        renderAllSilosTable(demoSilos);
    } finally {
        hideLoading();
    }
}

// Load data when page loads
document.addEventListener('DOMContentLoaded', function() {
    loadOverviewData();
    loadAllSilos();
    
    // Set up periodic refresh every 30 seconds - เหมือนกับ admin
    setInterval(() => {
        if (!document.hidden) {
            loadOverviewData();
            loadAllSilos();
        }
    }, 30000);
});

// Handle page visibility change - เหมือนกับ admin
document.addEventListener('visibilitychange', function() {
    if (!document.hidden) {
        loadOverviewData();
        loadAllSilos();
    }
});

// ฟังก์ชัน debug ข้อมูล - เหมือนกับ admin
async function debugData() {
    try {
        console.log('🐛 Debugging overview data...');
        
        // ตรวจสอบ endpoint volume_data
        const response = await fetch('/api/volume_data');
        const data = await response.json();
        console.log('📋 Volume data endpoint:', data);
        
        // ตรวจสอบจำนวนข้อมูล
        if (Array.isArray(data)) {
            console.log(`📈 Total silos from volume_data: ${data.length}`);
            
            // นับตามจังหวัด
            const provinceCount = {};
            data.forEach(silo => {
                const province = silo.province || 'Unknown';
                provinceCount[province] = (provinceCount[province] || 0) + 1;
            });
            console.log('🏢 Silos by province:', provinceCount);
        }
        
        alert('ตรวจสอบข้อมูลใน Console (F12) แล้ว');
        
    } catch (error) {
        console.error('Debug error:', error);
        alert('Debug failed: ' + error.message);
    }
}

// เพิ่มปุ่ม debug ใน HTML
function addDebugButton() {
    const headerStats = document.querySelector('.header-stats');
    if (headerStats) {
        const debugBtn = document.createElement('button');
        debugBtn.className = 'btn btn-secondary';
        debugBtn.innerHTML = '<i class="fas fa-bug"></i> Debug';
        debugBtn.onclick = debugData;
        debugBtn.style.marginLeft = '1rem';
        headerStats.appendChild(debugBtn);
    }
}

// เรียกใช้เมื่อโหลดหน้า
document.addEventListener('DOMContentLoaded', function() {
    addDebugButton();
});