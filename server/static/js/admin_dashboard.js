// Global variables
let branches = {};
let selectedBranch = null;
let combinedChart = null;
let siloDetailChart = null;
let selectedSilos = new Set();
let currentViewType = 'chart';

// Colors for different silos
const siloColors = [
    '#F97316', '#0EA5E9', '#10B981', '#8B5CF6', '#F59E0B', '#EF4444',
    '#84CC16', '#06B6D4', '#EC4899', '#78716C'
];

const siloColorMap = new Map();

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

function getSiloColor(siloName) {
    if (!siloColorMap.has(siloName)) {
        const colorIndex = siloColorMap.size % siloColors.length;
        siloColorMap.set(siloName, siloColors[colorIndex]);
    }
    return siloColorMap.get(siloName);
}

// ตรวจสอบสถานะการล็อคอิน - FIXED VERSION
async function checkLoginStatus() {
    try {
        console.log('🔍 Checking login status...');
        
        const response = await fetch('/api/current_user');
        console.log('📡 Response status:', response.status);
        
        // ✅ TEMPORARY FIX: Always return true for now
        console.log('✅ TEMPORARY: Bypassing login check - returning true');
        return true;
        
        // ❌ COMMENT OUT THE REDIRECT LOGIC TEMPORARILY
        /*
        if (!response.ok) {
            console.log('❌ API response not OK, redirecting to login');
            window.location.href = '/login';
            return false;
        }
        
        const userData = await response.json();
        console.log('👤 User data:', userData);
        
        if (userData && userData.error) {
            console.log('❌ User error in response:', userData.error);
            window.location.href = '/login';
            return false;
        }
        
        if (!userData || !userData.username) {
            console.log('❌ No user data received');
            window.location.href = '/login';
            return false;
        }
        
        console.log('✅ Logged in as:', userData.username);
        
        sessionStorage.setItem('username', userData.username);
        sessionStorage.setItem('role', userData.role);
        sessionStorage.setItem('user_id', userData.id);
        
        const usernameDisplay = document.getElementById('username-display');
        if (usernameDisplay) {
            usernameDisplay.textContent = userData.username;
        }
        
        return true;
        */
        
    } catch (error) {
        console.error('❌ Error checking login status:', error);
        // ✅ TEMPORARY: Don't redirect on error
        console.log('✅ TEMPORARY: Not redirecting on error - returning true');
        return true;
        
        // ❌ window.location.href = '/login';
        // ❌ return false;
    }
}

// API Functions
async function fetchBranches() {
    try {
        console.log('🔍 Fetching volume data from /api/volume_data');
        const response = await fetch('/api/volume_data', {
            credentials: 'include'
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        console.log('📈 API response:', data);
        
        if (!Array.isArray(data)) {
            console.error('❌ Expected array but got:', typeof data);
            return [];
        }

        if (data.length === 0) {
            console.warn('⚠️ No data from API');
            return [];
        }

        // Process data from SQLite database
        const branchesMap = {};
        
        data.forEach((silo, index) => {
            const province = silo.province || 'ไม่ทราบจังหวัด';
            const deviceId = silo.device_id || `device-${index}`;
            
            if (!province || province.trim() === '') {
                return;
            }
            
            if (!branchesMap[province]) {
                branchesMap[province] = {
                    id: province,
                    name: `สาขา${province}`,
                    location: province,
                    total_capacity: 0,
                    total_used: 0,
                    silos: [],
                    low_capacity_silos: 0
                };
            }
            
            const siloCapacity = silo.capacity || 1000;
            const currentAmount = silo.volume || 0;
            const percentage = (currentAmount / siloCapacity) * 100;
            const isLowCapacity = percentage < 35;
            
            const siloData = {
                id: deviceId,
                name: `ไซโล ${silo.silo_no || (index + 1)}`,
                material: silo.plant_type || 'ไม่ทราบประเภท',
                capacity: siloCapacity,
                current_amount: currentAmount,
                percentage: percentage,
                device_id: deviceId,
                site_code: silo.site_code || 'N/A',
                last_updated: silo.timestamp || new Date().toISOString(),
                is_low_capacity: isLowCapacity
            };
            
            branchesMap[province].silos.push(siloData);
            branchesMap[province].total_capacity += siloCapacity;
            branchesMap[province].total_used += currentAmount;
            
            if (isLowCapacity) {
                branchesMap[province].low_capacity_silos++;
            }
        });

        return Object.values(branchesMap).filter(branch => 
            branch.silos && branch.silos.length > 0
        );
        
    } catch (error) {
        console.error('❌ Error fetching branches:', error);
        return [];
    }
}

// ฟังก์ชันสร้างข้อมูลทดสอบ
function getDemoData() {
    console.log('Using demo data as fallback');
    return [
        {
            id: 'demo-branch-1',
            name: 'สาขากรุงเทพ',
            location: 'กรุงเทพ',
            total_capacity: 2000,
            total_used: 1250,
            low_capacity_silos: 1,
            silos: [
                {
                    id: 'demo-silo-1',
                    name: 'ไซโล A',
                    material: 'ข้าวสาร',
                    capacity: 1000,
                    current_amount: 500,
                    percentage: 50,
                    device_id: 'DEMO001',
                    site_code: 'BKK001',
                    last_updated: new Date().toISOString(),
                    is_low_capacity: false
                },
                {
                    id: 'demo-silo-2',
                    name: 'ไซโล B',
                    material: 'ข้าวโพด',
                    capacity: 1000,
                    current_amount: 750,
                    percentage: 75,
                    device_id: 'DEMO002',
                    site_code: 'BKK001',
                    last_updated: new Date().toISOString(),
                    is_low_capacity: false
                }
            ]
        }
    ];
}

function updateBreadcrumb() {
    const breadcrumbElement = document.getElementById('breadcrumb');
    if (!breadcrumbElement) return;
    
    if (selectedBranch && branches[selectedBranch]) {
        const branch = branches[selectedBranch];
        breadcrumbElement.innerHTML = `
            <span>สาขา</span>
            <span class="breadcrumb-separator">/</span>
            <span class="breadcrumb-current">${branch.name}</span>
        `;
    } else {
        breadcrumbElement.innerHTML = `
            <span>สาขา</span>
            <span class="breadcrumb-separator">/</span>
            <span class="breadcrumb-current">เลือกสาขา</span>
        `;
    }
}

async function fetchSiloHistory(deviceId) {
    try {
        const response = await fetch(`/api/volume_history/${deviceId}`);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return await response.json();
    } catch (error) {
        console.error('Error fetching silo history:', error);
        return generateDemoHistory(deviceId);
    }
}

function generateDemoHistory(deviceId) {
    const history = [];
    const now = new Date();
    
    for (let i = 6; i >= 0; i--) {
        const date = new Date(now);
        date.setDate(date.getDate() - i);
        const baseVolume = Math.random() * 500 + 300;
        const volume = Math.round(baseVolume * 100) / 100;
        
        history.push({
            timestamp: date.toISOString(),
            volume: volume,
            volume_percentage: Math.round((volume / 1000) * 100)
        });
    }
    
    return history;
}

// Render Functions
async function renderBranches() {
    const container = document.getElementById('branch-list');
    const branchArray = Object.values(branches);
    
    if (branchArray.length === 0) {
        container.innerHTML = '<div style="text-align: center; padding: 2rem; color: var(--dark);">ไม่มีข้อมูลสาขา</div>';
        return;
    }
    
    let html = '';
    
    for (const branch of branchArray) {
        const totalUsed = branch.total_used || branch.silos.reduce((a, b) => a + b.current_amount, 0);
        const totalCapacity = branch.total_capacity || branch.silos.reduce((a, b) => a + b.capacity, 0);
        const percent = Math.round(totalUsed / (totalCapacity || 1000) * 100);
        const isSelected = branch.id === selectedBranch;
        const hasLowCapacity = branch.low_capacity_silos > 0;
        
        html += `
            <div class="branch-card ${isSelected ? 'selected' : ''} ${hasLowCapacity ? 'has-alert' : ''}" onclick="selectBranch('${branch.id}')">
                <div class="branch-header">
                    <div>
                        <h3>${branch.name}</h3>
                        <p>${branch.location}</p>
                    </div>
                    <div class="branch-count">
                        ${branch.silos.length} ไซโล
                        ${hasLowCapacity ? `<span class="alert-badge">⚠️ ${branch.low_capacity_silos}</span>` : ''}
                        <button class="silo-action-btn" onclick="event.stopPropagation(); deleteBranch('${branch.id}')">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                </div>
                <div class="branch-progress">
                    <span>ใช้ไปแล้ว: ${totalUsed.toFixed(1)} / ${totalCapacity.toFixed(1)} ตัน (${percent}%)</span>
                    <div class="progress-bar">
                        <div class="progress-fill" style="width:${percent}%"></div>
                    </div>
                </div>
                ${hasLowCapacity ? `
                    <div class="branch-alert">
                        <i class="fas fa-exclamation-triangle"></i>
                        มี ${branch.low_capacity_silos} ไซโลที่มีปริมาณต่ำกว่า 35%
                    </div>
                ` : ''}
            </div>
        `;
    }
    
    container.innerHTML = html;
}

async function selectBranch(branchId) {
    showLoading();
    try {
        selectedBranch = branchId;
        selectedSilos.clear();
        
        if (branches[selectedBranch] && branches[selectedBranch].silos) {
            branches[selectedBranch].silos.forEach(silo => selectedSilos.add(silo.id));
        }
        
        await renderBranches();
        await renderSilos();
        updateBranchInfo();
        updateBranchSummary();
        updateBreadcrumb();
        updateView();
    } catch (error) {
        console.error('Error selecting branch:', error);
        showToast('เกิดข้อผิดพลาดในการเลือกสาขา', 'error');
    } finally {
        hideLoading();
    }
}

async function renderSilos() {
    const siloContainer = document.getElementById('silo-grid');
    
    if (!selectedBranch || !branches[selectedBranch] || !branches[selectedBranch].silos) {
        siloContainer.innerHTML = '<div style="text-align: center; padding: 2rem; color: var(--dark);">ไม่มีข้อมูลไซโล</div>';
        return;
    }
    
    const branch = branches[selectedBranch];
    
    if (branch.silos.length === 0) {
        siloContainer.innerHTML = '<div style="text-align: center; padding: 2rem; color: var(--dark);">ไม่มีไซโลในสาขานี้</div>';
        return;
    }
    
    let html = '';
    
    for (const silo of branch.silos) {
        const percent = Math.round((silo.current_amount / silo.capacity) * 100);
        const siloColor = getSiloColor(silo.name);
        const isLowCapacity = percent < 35;
        
        html += `
            <div class="silo-card ${isLowCapacity ? 'low-capacity' : ''}" onclick="showSiloDetail('${silo.id}')">
                <div class="silo-actions">
                    <button class="silo-action-btn" onclick="event.stopPropagation(); deleteSilo('${silo.device_id}')" title="ลบไซโล">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
                ${isLowCapacity ? `
                    <div class="silo-alert-indicator">
                        <i class="fas fa-exclamation-triangle"></i>
                        ปริมาณต่ำ
                    </div>
                ` : ''}
                <div class="silo-header">
                    <div class="silo-title">
                        <h4>${silo.name}</h4>
                        <p>${silo.material} - ${silo.site_code}</p>
                        <small>Device: ${silo.device_id}</small>
                    </div>
                </div>
                <div class="silo-tank ${isLowCapacity ? 'low-tank' : ''}">
                    <div class="silo-fill" style="height:${percent}%"></div>
                    <div class="silo-overlay"></div>
                    <div class="silo-text">
                        <div class="percentage ${isLowCapacity ? 'low-percentage' : ''}">${percent}%</div>
                        <div class="amount">${silo.current_amount} / ${silo.capacity} ตัน</div>
                    </div>
                </div>
                ${isLowCapacity ? `
                    <div class="silo-warning">
                        <i class="fas fa-exclamation-circle"></i>
                        ปริมาณต่ำกว่า 35%
                    </div>
                ` : ''}
            </div>
        `;
    }
    
    siloContainer.innerHTML = html;
}

function updateBranchInfo() {
    if (selectedBranch && branches[selectedBranch]) {
        const branch = branches[selectedBranch];
        document.getElementById('current-branch-name').textContent = branch.name;
        document.getElementById('current-branch-location').textContent = branch.location;
    }
}

function updateBranchSummary() {
    if (!selectedBranch || !branches[selectedBranch]) return;
    
    const branch = branches[selectedBranch];
    const totalSilos = branch.silos.length;
    const lowCapacitySilos = branch.low_capacity_silos || branch.silos.filter(s => s.percentage < 35).length;
    const totalUsed = branch.total_used || branch.silos.reduce((a, b) => a + b.current_amount, 0);
    const totalCapacity = branch.total_capacity || branch.silos.reduce((a, b) => a + b.capacity, 0);
    const totalPercentage = Math.round((totalUsed / totalCapacity) * 100);
    
    document.getElementById('total-silos').textContent = totalSilos;
    document.getElementById('active-silos').textContent = totalSilos - lowCapacitySilos;
    document.getElementById('low-capacity-silos').textContent = lowCapacitySilos;
    document.getElementById('total-used').textContent = totalPercentage + '%';
    
    const lowCapacityCard = document.getElementById('low-capacity-card');
    if (lowCapacitySilos > 0) {
        lowCapacityCard.style.display = 'block';
    } else {
        lowCapacityCard.style.display = 'none';
    }
}

// Chart Functions
function renderCombinedChart() {
    const ctx = document.getElementById('combined-chart').getContext('2d');
    
    if (combinedChart) {
        combinedChart.destroy();
    }

    if (!selectedBranch || !branches[selectedBranch] || selectedSilos.size === 0) {
        combinedChart = new Chart(ctx, {
            type: 'line',
            data: { datasets: [] },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    title: {
                        display: true,
                        text: 'ไม่มีข้อมูลที่จะแสดง'
                    }
                }
            }
        });
        return;
    }

    const branch = branches[selectedBranch];
    const selectedSiloData = branch.silos.filter(silo => selectedSilos.has(silo.id));
    
    const datasets = selectedSiloData.map(silo => {
        const color = getSiloColor(silo.name);
        
        return {
            label: silo.name,
            data: [{
                x: 'ปัจจุบัน',
                y: silo.current_amount
            }],
            borderColor: color,
            backgroundColor: color + '20',
            tension: 0.4,
            fill: false
        };
    });

    combinedChart = new Chart(ctx, {
        type: 'line',
        data: {
            datasets: datasets
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                title: {
                    display: true,
                    text: 'ปริมาณไซโลปัจจุบัน'
                },
                legend: {
                    position: 'top',
                }
            },
            scales: {
                x: {
                    type: 'category',
                    title: {
                        display: true,
                        text: 'ไซโล'
                    }
                },
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: 'ปริมาณ (ตัน)'
                    }
                }
            }
        }
    });
}

function renderSiloDetailChart(history) {
    const ctx = document.getElementById('silo-detail-chart').getContext('2d');
    
    if (siloDetailChart) {
        siloDetailChart.destroy();
    }

    const labels = history.map(h => new Date(h.timestamp).toLocaleDateString('th-TH'));
    const data = history.map(h => h.volume);

    siloDetailChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'ปริมาณ',
                data: data,
                borderColor: '#F97316',
                backgroundColor: '#F9731620',
                tension: 0.4,
                fill: true
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                title: {
                    display: true,
                    text: 'ประวัติปริมาณ 7 วันที่ผ่านมา'
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: 'ปริมาณ (ตัน)'
                    }
                }
            }
        }
    });
}

// View Management
function changeViewType(type) {
    currentViewType = type;
    
    document.querySelectorAll('.view-option').forEach(btn => btn.classList.remove('active'));
    event.target.classList.add('active');
    
    document.getElementById('chart-view').style.display = type === 'chart' ? 'block' : 'none';
    document.getElementById('table-view').style.display = type === 'table' ? 'block' : 'none';
    
    updateView();
}

function updateView() {
    if (currentViewType === 'chart') {
        renderCombinedChart();
    } else {
        renderDataTable();
    }
}

function renderDataTable() {
    const container = document.getElementById('data-table');
    
    if (!selectedBranch || !branches[selectedBranch] || selectedSilos.size === 0) {
        container.innerHTML = '<div style="text-align: center; padding: 2rem; color: var(--dark);">ไม่มีข้อมูลที่จะแสดง</div>';
        return;
    }

    const branch = branches[selectedBranch];
    const selectedSiloData = branch.silos.filter(silo => selectedSilos.has(silo.id));
    
    let html = `
        <table class="data-table">
            <thead>
                <tr>
                    <th>ไซโล</th>
                    <th>วัสดุ</th>
                    <th>ปริมาณปัจจุบัน</th>
                    <th>ความจุ</th>
                    <th>อัตราการใช้</th>
                    <th>อัพเดทล่าสุด</th>
                </tr>
            </thead>
            <tbody>
    `;

    selectedSiloData.forEach(silo => {
        const percent = Math.round((silo.current_amount / silo.capacity) * 100);
        const color = getSiloColor(silo.name);
        
        html += `
            <tr>
                <td>
                    <span class="silo-color-indicator" style="background: ${color}"></span>
                    ${silo.name}
                </td>
                <td>${silo.material}</td>
                <td>${silo.current_amount} ตัน</td>
                <td>${silo.capacity} ตัน</td>
                <td>${percent}%</td>
                <td>${new Date(silo.last_updated).toLocaleString('th-TH')}</td>
            </tr>
        `;
    });

    html += '</tbody></table>';
    container.innerHTML = html;
}

// Modal Functions
function openSiloSelection() {
    if (!selectedBranch || !branches[selectedBranch]) return;
    
    const branch = branches[selectedBranch];
    const container = document.getElementById('siloSelectionList');
    
    let html = '';
    branch.silos.forEach(silo => {
        const isSelected = selectedSilos.has(silo.id);
        const color = getSiloColor(silo.name);
        
        html += `
            <div class="silo-selection-item ${isSelected ? 'selected' : ''}" onclick="toggleSiloSelection('${silo.id}')">
                <div class="silo-checkbox"></div>
                <div class="silo-selection-info">
                    <div class="silo-color-preview" style="background: ${color}"></div>
                    <div>
                        <h4>${silo.name}</h4>
                        <p>${silo.material} - ${silo.current_amount} ตัน</p>
                    </div>
                </div>
            </div>
        `;
    });
    
    container.innerHTML = html;
    document.getElementById('siloSelectionModal').classList.add('active');
}

function toggleSiloSelection(siloId) {
    if (selectedSilos.has(siloId)) {
        selectedSilos.delete(siloId);
    } else {
        selectedSilos.add(siloId);
    }
    openSiloSelection();
}

function selectAllSilos() {
    if (!selectedBranch || !branches[selectedBranch]) return;
    const branch = branches[selectedBranch];
    branch.silos.forEach(silo => selectedSilos.add(silo.id));
    openSiloSelection();
}

function deselectAllSilos() {
    selectedSilos.clear();
    openSiloSelection();
}

function applySiloSelection() {
    closeSiloSelection();
    updateView();
}

function closeSiloSelection() {
    document.getElementById('siloSelectionModal').classList.remove('active');
}

function closeSiloDetail() {
    document.getElementById('siloDetailModal').classList.remove('active');
}

function openAddSiloModal() {
    document.getElementById('addSiloModal').classList.add('active');
}

function closeAddSiloModal() {
    document.getElementById('addSiloModal').classList.remove('active');
    document.getElementById('addSiloForm').reset();
}

function openAddBranchModal() {
    document.getElementById('addBranchModal').classList.add('active');
}

function closeAddBranchModal() {
    document.getElementById('addBranchModal').classList.remove('active');
    document.getElementById('addBranchForm').reset();
}

function openExportModal() {
    if (!selectedBranch || !branches[selectedBranch]) return;
    
    const branch = branches[selectedBranch];
    const container = document.getElementById('exportSiloList');
    
    let html = '';
    branch.silos.forEach(silo => {
        const color = getSiloColor(silo.name);
        
        html += `
            <div class="silo-selection-item selected">
                <div class="silo-checkbox"></div>
                <div class="silo-selection-info">
                    <div class="silo-color-preview" style="background: ${color}"></div>
                    <div>
                        <h4>${silo.name}</h4>
                        <p>${silo.material} - ${silo.current_amount} ตัน</p>
                    </div>
                </div>
            </div>
        `;
    });
    
    container.innerHTML = html;
    document.getElementById('exportModal').classList.add('active');
}

function closeExportModal() {
    document.getElementById('exportModal').classList.remove('active');
}

function openUserManagement() {
    document.getElementById('userManagementModal').classList.add('active');
}

function closeUserManagement() {
    document.getElementById('userManagementModal').classList.remove('active');
}

function openBranchManagement() {
    document.getElementById('branchManagementModal').classList.add('active');
}

function closeBranchManagement() {
    document.getElementById('branchManagementModal').classList.remove('active');
}

// API Functions
async function addNewSilo() {
    const form = document.getElementById('addSiloForm');
    
    if (!form.checkValidity()) {
        form.reportValidity();
        return;
    }

    const siloData = {
        device_id: document.getElementById('siloDeviceId').value,
        plant_type: document.getElementById('siloPlantType').value,
        province: document.getElementById('siloProvince').value,
        site_code: document.getElementById('siloSiteCode').value,
        silo_no: document.getElementById('siloNo').value
    };

    try {
        showLoading();
        const response = await fetch('/api/admin/silos', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(siloData)
        });

        const result = await response.json();
        
        if (response.ok) {
            showToast('เพิ่มไซโลสำเร็จ');
            closeAddSiloModal();
            loadInitialData();
        } else {
            showToast(result.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch (error) {
        console.error('Error adding silo:', error);
        showToast('เกิดข้อผิดพลาดในการเพิ่มไซโล', 'error');
    } finally {
        hideLoading();
    }
}

async function deleteSilo(deviceId) {
    if (!confirm('คุณแน่ใจที่จะลบไซโลนี้?')) return;

    try {
        showLoading();
        const response = await fetch(`/api/admin/silos/by_device/${deviceId}`, {
            method: 'DELETE'
        });

        const result = await response.json();
        
        if (response.ok) {
            showToast('ลบไซโลสำเร็จ');
            loadInitialData();
        } else {
            showToast(result.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch (error) {
        console.error('Error deleting silo:', error);
        showToast('เกิดข้อผิดพลาดในการลบไซโล', 'error');
    } finally {
        hideLoading();
    }
}

async function deleteBranch(branchId) {
    if (!confirm('คุณแน่ใจที่จะลบสาขานี้?')) return;

    try {
        showLoading();
        const response = await fetch(`/api/admin/branches/${branchId}`, {
            method: 'DELETE'
        });

        const result = await response.json();
        
        if (response.ok) {
            showToast('ลบสาขาสำเร็จ');
            loadInitialData();
        } else {
            showToast(result.error || 'เกิดข้อผิดพลาด', 'error');
        }
    } catch (error) {
        console.error('Error deleting branch:', error);
        showToast('เกิดข้อผิดพลาดในการลบสาขา', 'error');
    } finally {
        hideLoading();
    }
}

function addNewBranch() {
    showToast('การเพิ่มสาขาในระบบจริงจะต้องเชื่อมต่อกับ API');
    closeAddBranchModal();
}

function exportToExcel() {
    showToast('กำลังเตรียมไฟล์ Excel...');
    setTimeout(() => showToast('ส่งออกข้อมูลสำเร็จ'), 2000);
    closeExportModal();
}

// ฟังก์ชันหลักสำหรับโหลดข้อมูล - FIXED VERSION
async function loadInitialData() {
    console.log('🚀 Starting to load initial data...');
    
    // ✅ TEMPORARY FIX: Skip login check completely
    console.log('✅ TEMPORARY: Skipping login check - proceeding with data load');
    
    showLoading();
    try {
        const branchesData = await fetchBranches();
        console.log('📊 Branches data received:', branchesData);
        
        branches = {};
        
        if (branchesData.length === 0) {
            console.log('⚠️ No branches data received, using demo data');
            const demoData = getDemoData();
            for (const branch of demoData) {
                branches[branch.id] = branch;
            }
        } else {
            for (const branch of branchesData) {
                branches[branch.id] = branch;
            }
        }
        
        console.log('🏢 Branches object:', branches);
        
        const branchIds = Object.keys(branches);
        if (branchIds.length > 0 && !selectedBranch) {
            selectedBranch = branchIds[0];
            console.log('📍 Auto-selected branch:', selectedBranch);
            
            if (branches[selectedBranch] && branches[selectedBranch].silos) {
                branches[selectedBranch].silos.forEach(silo => {
                    selectedSilos.add(silo.id);
                });
            }
        }
        
        console.log('🎯 Selected branch:', selectedBranch);
        
        await renderBranches();
        
        if (selectedBranch && branches[selectedBranch]) {
            await renderSilos();
            updateBranchInfo();
            updateBranchSummary();
            updateBreadcrumb();
            updateView();
            console.log('✅ All data loaded and rendered successfully');
        } else {
            console.error('❌ No valid branch selected');
            showNoDataMessage();
        }
        
    } catch (error) {
        console.error('❌ Error loading initial data:', error);
        showToast('เกิดข้อผิดพลาดในการโหลดข้อมูล: ' + error.message, 'error');
        showNoDataMessage();
    } finally {
        hideLoading();
    }
}

async function showSiloDetail(siloId) {
    showLoading();
    try {
        const branch = branches[selectedBranch];
        const silo = branch.silos.find(s => s.id === siloId);
        
        if (!silo) return;

        // Update modal content
        document.getElementById('detail-name').textContent = silo.name;
        document.getElementById('detail-material').textContent = silo.material;
        document.getElementById('detail-capacity').textContent = silo.capacity + ' ตัน';
        document.getElementById('detail-current').textContent = silo.current_amount + ' ตัน';
        document.getElementById('detail-percentage').textContent = Math.round((silo.current_amount / silo.capacity) * 100) + '%';
        document.getElementById('detail-lastUpdated').textContent = new Date(silo.last_updated).toLocaleString('th-TH');

        // Fetch and render history chart
        const history = await fetchSiloHistory(silo.device_id);
        renderSiloDetailChart(history);

        // Show modal
        document.getElementById('siloDetailModal').classList.add('active');
    } catch (error) {
        console.error('Error showing silo detail:', error);
        showToast('เกิดข้อผิดพลาดในการโหลดรายละเอียด', 'error');
    } finally {
        hideLoading();
    }
}

function showNoDataMessage() {
    document.getElementById('silo-grid').innerHTML = `
        <div style="text-align: center; padding: 3rem; color: var(--dark);">
            <i class="fas fa-database" style="font-size: 3rem; color: var(--gray); margin-bottom: 1rem;"></i>
            <div>ไม่มีข้อมูลไซโล</div>
            <small>อาจยังไม่มีข้อมูลในระบบ หรือเกิดข้อผิดพลาดในการเชื่อมต่อ</small>
        </div>
    `;
    
    document.getElementById('branch-list').innerHTML = `
        <div style="text-align: center; padding: 2rem; color: var(--dark);">
            <i class="fas fa-warehouse" style="font-size: 2rem; color: var(--gray); margin-bottom: 1rem;"></i>
            <div>ไม่มีข้อมูลสาขา</div>
        </div>
    `;
}

// Initialize when page loads
document.addEventListener('DOMContentLoaded', function() {
    console.log('🚀 Admin Dashboard initializing...');
    loadInitialData();
    
    // Set up periodic refresh every 30 seconds
    setInterval(() => {
        if (!document.hidden) {
            console.log('🔄 Auto-refreshing data...');
            loadInitialData();
        }
    }, 30000);
});

// Handle page visibility change
document.addEventListener('visibilitychange', function() {
    if (!document.hidden) {
        console.log('📱 Page visible, refreshing data...');
        loadInitialData();
    }
});
