// --- ICONS COMPONENTS ---
const ChevronDown = ({ size = 18, className = "" }) => (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}><path d="m6 9 6 6 6-6"/></svg>
);
const ChevronLeft = ({ size = 24, className = "" }) => (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}><path d="m15 18-6-6 6-6"/></svg>
);
const ChevronRight = ({ size = 24, className = "" }) => (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}><path d="m9 18 6-6-6-6"/></svg>
);
const CheckIcon = ({ size = 20, className = "" }) => (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" className={className}><polyline points="20 6 9 17 4 12"/></svg>
);
const XIcon = ({ size = 20, className = "" }) => (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" className={className}><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
);
const ArrowLeftIcon = ({ size = 20, className = "" }) => (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}><path d="m12 19-7-7 7-7"/><path d="M19 12H5"/></svg>
);

// --- COMPONENT: BEDROOM ANALYSIS CARD ---
const BedroomAnalysisCard = ({ data = [], selectedReq = null, onBack }) => {
    const [selectedType, setSelectedType] = React.useState('BEDROOM');
    const [selectedStatus, setSelectedStatus] = React.useState('ALL');
    const [isTypeDropdownOpen, setIsTypeDropdownOpen] = React.useState(false);
    const [isStatusDropdownOpen, setIsStatusDropdownOpen] = React.useState(false);
    const typeDropdownRef = React.useRef(null);
    const statusDropdownRef = React.useRef(null);

    React.useEffect(() => {
        function handleClickOutside(event) {
            if (typeDropdownRef.current && !typeDropdownRef.current.contains(event.target)) setIsTypeDropdownOpen(false);
            if (statusDropdownRef.current && !statusDropdownRef.current.contains(event.target)) setIsStatusDropdownOpen(false);
        }
        document.addEventListener("mousedown", handleClickOutside);
        return () => document.removeEventListener("mousedown", handleClickOutside);
    }, []);

    const roomTypes = ['BEDROOM', 'LDK', 'Japan Style Room', 'Study Room', 'Storage', 'Balcony', 'Bathroom', '1 Toilet', '2 Toilet', '3 Toilet'];
    const statusOptions = ['ALL', 'Success', 'Failed'];

    const stats = React.useMemo(() => {
        let small = 0, good = 0, big = 0;
        let targetKey = 'bedroom';
        switch(selectedType) {
            case 'BEDROOM': targetKey = 'bedroom'; break;
            case 'LDK': targetKey = 'ldk'; break;
            case 'Japan Style Room': targetKey = 'japan'; break;
            case 'Study Room': targetKey = 'study'; break;
            case 'Storage': targetKey = 'storage'; break;
            case 'Balcony': targetKey = 'balcony'; break;
            case 'Bathroom': targetKey = 'bathroom'; break;
            case '1 Toilet': targetKey = 'toilet_1'; break;
            case '2 Toilet': targetKey = 'toilet_2'; break;
            case '3 Toilet': targetKey = 'toilet_3'; break;
            default: targetKey = 'bedroom';
        }
        const filteredRequests = data.filter(req => {
            if (selectedStatus === 'Success') return req.isSuccess;
            if (selectedStatus === 'Failed') return !req.isSuccess;
            return true;
        });
        filteredRequests.forEach(req => {
            if (req.room_consistency && req.room_consistency[targetKey]) {
                const consistency = req.room_consistency[targetKey];
                if (consistency.too_small === 1) small++;
                else if (consistency.too_big === 1) big++;
                else if (consistency.good === 1) good++;
            }
        });
        if (selectedStatus === 'Success') { small = 0; big = 0; } 
        else if (selectedStatus === 'Failed') { good = 0; }
        const total = small + good + big;
        return { small, good, big, total, pctSmall: total ? Math.round((small / total) * 100) : 0, pctGood: total ? Math.round((good / total) * 100) : 0, pctBig: total ? Math.round((big / total) * 100) : 0 };
    }, [data, selectedType, selectedStatus]);

    // --- HELPER: Calculate Label Position based on Angles ---
    const getLabelStyle = (pct, startPct) => {
        if (pct <= 0) return { display: 'none' };
        const midAngleDeg = (startPct + pct / 2) * 3.6; 
        const rad = (midAngleDeg - 90) * (Math.PI / 180);
        const radius = 120; 
        const x = Math.cos(rad) * radius;
        const y = Math.sin(rad) * radius;
        return {
            transform: `translate(${x}px, ${y}px)`,
            position: 'absolute',
            zIndex: 10
        };
    };

    const pieChartStyle = {
        background: stats.total === 0 ? '#F3F4F6' : `conic-gradient(#EAB308 0% ${stats.pctSmall}%, #7C3AED ${stats.pctSmall}% ${stats.pctSmall + stats.pctGood}%, #F472B6 ${stats.pctSmall + stats.pctGood}% 100%)`,
        borderRadius: '50%', transform: 'rotate(0deg)'
    };

    if (selectedReq) {
        const errorRooms = [];
        if (selectedReq.room_consistency) {
            for (const [key, val] of Object.entries(selectedReq.room_consistency)) {
                if (val.good !== 1) {
                    let label = key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
                    if(key === 'ldk') label = 'LDK';
                    errorRooms.push({ label, status: val });
                }
            }
        }
        const BASE_PATH = '/static/floorplan_app/module_Survey/';
        const imgPath = `${BASE_PATH}${selectedReq._fileIndex}.png`;
        return (
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-8 flex flex-col h-full overflow-hidden relative react-fade-in">
                <div className="flex justify-between items-center mb-8 pb-4 border-b border-gray-100">
                    <h2 className="text-blue-600 font-bold text-2xl uppercase tracking-wide">{selectedReq.request_id}</h2>
                    <button onClick={onBack} className="flex items-center gap-2 text-sm font-medium text-gray-500 hover:text-gray-800 transition-colors bg-gray-100 hover:bg-gray-200 px-3 py-2 rounded-lg"><ArrowLeftIcon size={16} /> Back</button>
                </div>
                <div className="w-full h-48 bg-gray-100 rounded-lg border border-gray-200 mb-6 flex items-center justify-center overflow-hidden">
                    <img src={imgPath} alt="Plan" className="h-full object-contain" onError={(e) => {e.target.onerror = null; e.target.src='https://placehold.co/300x200?text=No+Image'}} />
                </div>
                <div className="w-full flex-grow overflow-y-auto custom-scrollbar">
                    <table className="w-full text-left border-collapse">
                        <thead className="sticky top-0 bg-white">
                            <tr className="border-b border-gray-200 text-xs font-bold text-gray-400 uppercase tracking-wider">
                                <th className="py-4 pr-4">ROOM TYPE</th>
                                <th className="py-4 px-2 text-center w-24">TOO SMALL</th>
                                <th className="py-4 px-2 text-center w-24">GOOD</th>
                                <th className="py-4 px-2 text-center w-24">TOO BIG</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-50">
                            {errorRooms.length > 0 ? (
                                errorRooms.map((room, idx) => (
                                    <tr key={idx} className="hover:bg-gray-50 transition-colors">
                                        <td className="py-4 font-medium text-gray-800 text-sm">{room.label}</td>
                                        <td className="py-4 text-center"><div className="flex justify-center">{room.status.too_small === 1 ? <CheckIcon className="text-red-500"/> : <XIcon className="text-gray-200"/>}</div></td>
                                        <td className="py-4 text-center"><div className="flex justify-center"><XIcon className="text-gray-200"/></div></td>
                                        <td className="py-4 text-center"><div className="flex justify-center">{room.status.too_big === 1 ? <CheckIcon className="text-red-500"/> : <XIcon className="text-gray-200"/>}</div></td>
                                    </tr>
                                ))
                            ) : ( <tr><td colSpan="4" className="py-12 text-center text-green-500 font-medium">No inconsistencies found!</td></tr> )}
                        </tbody>
                    </table>
                </div>
            </div>
        );
    }

    return (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-8 flex flex-col h-full overflow-hidden relative">
            <div className="flex justify-between items-center mb-10">
                <h2 className="text-gray-800 font-bold text-xl uppercase tracking-wide">{selectedType}</h2>
                <div className="flex gap-3">
                     {/* Status Dropdown */}
                     <div className="relative dropdown-menu-container" ref={statusDropdownRef}>
                        <button onClick={() => setIsStatusDropdownOpen(!isStatusDropdownOpen)} className={`flex items-center justify-between gap-3 px-5 py-3 bg-white border rounded-lg text-base hover:bg-gray-50 min-w-[120px] transition-colors font-medium ${selectedStatus !== 'ALL' ? 'border-blue-500 text-blue-600' : 'border-gray-200 text-gray-600'}`}>
                            <span className="truncate">{selectedStatus}</span>
                            <ChevronDown size={18} className={`transition-transform flex-shrink-0 ${isStatusDropdownOpen ? 'rotate-180' : ''}`} />
                        </button>
                        {isStatusDropdownOpen && (
                            <div className="absolute top-full mt-2 right-0 w-32 bg-white border border-gray-200 rounded-lg shadow-lg z-30">
                                {statusOptions.map(status => (
                                    <button key={status} onClick={() => { setSelectedStatus(status); setIsStatusDropdownOpen(false); }} className={`w-full text-left px-5 py-3 text-base hover:bg-gray-50 text-gray-700 ${selectedStatus === status ? 'bg-blue-50 text-blue-600 font-semibold' : ''}`}>{status}</button>
                                ))}
                            </div>
                        )}
                    </div>
                    {/* Room Type Dropdown */}
                    <div className="relative dropdown-menu-container" ref={typeDropdownRef}>
                        <button onClick={() => setIsTypeDropdownOpen(!isTypeDropdownOpen)} className="flex items-center justify-between gap-3 px-5 py-3 bg-white border border-gray-200 rounded-lg text-base text-gray-600 hover:bg-gray-50 min-w-[145px] transition-colors font-medium">
                            <span className="truncate max-w-[120px]">{selectedType}</span>
                            <ChevronDown size={18} className={`transition-transform flex-shrink-0 ${isTypeDropdownOpen ? 'rotate-180' : ''}`} />
                        </button>
                        {isTypeDropdownOpen && (
                            <div className="absolute top-full mt-2 right-0 w-56 bg-white border border-gray-200 rounded-lg shadow-lg z-20 max-h-60 overflow-y-auto custom-scrollbar">
                                {roomTypes.map(type => (
                                    <button key={type} onClick={() => { setSelectedType(type); setIsTypeDropdownOpen(false); }} className={`w-full text-left px-5 py-3 text-base hover:bg-gray-50 text-gray-700 ${selectedType === type ? 'bg-blue-50 text-blue-600 font-semibold' : ''}`}>{type}</button>
                                ))}
                            </div>
                        )}
                    </div>
                </div>
            </div>
            
            <div className="w-full mb-12">
                <div className="grid grid-cols-4 gap-6 pb-6 border-b border-gray-100">
                    <div className="text-sm font-bold text-gray-400 uppercase text-center">ROOM TYPE</div>
                    <div className="text-sm font-bold text-gray-400 uppercase text-center">TOO SMALL</div>
                    <div className="text-sm font-bold text-gray-400 uppercase text-center">GOOD</div>
                    <div className="text-sm font-bold text-gray-400 uppercase text-center">TOO BIG</div>
                </div>
                <div className="grid grid-cols-4 gap-6 py-8 items-center">
                    <div className="text-lg font-bold text-gray-900 text-center truncate px-2" title={selectedType}>{selectedType}</div>
                    <div className="text-3xl font-bold text-gray-900 text-center">{stats.small}</div>
                    <div className="text-3xl font-bold text-gray-900 text-center">{stats.good}</div>
                    <div className="text-3xl font-bold text-gray-900 text-center">{stats.big}</div>
                </div>
            </div>

            {selectedStatus === 'ALL' && (
                <div className="flex-grow flex flex-row items-center justify-center gap-16 -translate-y-4">
                    <div className="relative w-[24rem] h-[24rem] shadow-sm flex-shrink-0 transition-all duration-500" style={pieChartStyle}>
                        <div className="absolute inset-0 flex items-center justify-center">
                            {stats.total > 0 ? (
                                <>
                                    <span style={getLabelStyle(stats.pctSmall, 0)} className="text-white font-bold text-4xl drop-shadow-md flex items-center justify-center">{stats.pctSmall}%</span>
                                    <span style={getLabelStyle(stats.pctGood, stats.pctSmall)} className="text-white font-bold text-4xl drop-shadow-md flex items-center justify-center">{stats.pctGood}%</span>
                                    <span style={getLabelStyle(stats.pctBig, stats.pctSmall + stats.pctGood)} className="text-white font-bold text-4xl drop-shadow-md flex items-center justify-center">{stats.pctBig}%</span>
                                </>
                            ) : <span className="text-gray-400 font-bold text-5xl">0%</span>}
                        </div>
                    </div>
                    <div className="flex flex-col justify-center gap-10">
                        <div className="flex items-start gap-4">
                            <span className={`w-6 h-6 rounded-full mt-1 shadow-sm ${stats.total > 0 && stats.small > 0 ? 'bg-yellow-500' : 'bg-gray-300'}`}></span>
                            <div className="flex flex-col">
                                <span className="text-sm font-bold text-gray-400 uppercase mb-1">TOO SMALL</span>
                                <div className="flex items-baseline gap-2">
                                    <span className="text-3xl font-bold text-gray-800">{stats.pctSmall}%</span>
                                    <span className="text-gray-500 text-xl font-medium">({stats.small})</span>
                                </div>
                            </div>
                        </div>
                        <div className="flex items-start gap-4">
                            <span className={`w-6 h-6 rounded-full mt-1 shadow-sm ${stats.total > 0 && stats.good > 0 ? 'bg-purple-600' : 'bg-gray-300'}`}></span>
                            <div className="flex flex-col">
                                <span className="text-sm font-bold text-gray-400 uppercase mb-1">GOOD</span>
                                <div className="flex items-baseline gap-2">
                                    <span className="text-3xl font-bold text-gray-800">{stats.pctGood}%</span>
                                    <span className="text-gray-500 text-xl font-medium">({stats.good})</span>
                                </div>
                            </div>
                        </div>
                        <div className="flex items-start gap-4">
                            <span className={`w-6 h-6 rounded-full mt-1 shadow-sm ${stats.total > 0 && stats.big > 0 ? 'bg-pink-400' : 'bg-gray-300'}`}></span>
                            <div className="flex flex-col">
                                <span className="text-sm font-bold text-gray-400 uppercase mb-1">TOO BIG</span>
                                <div className="flex items-baseline gap-2">
                                    <span className="text-3xl font-bold text-gray-800">{stats.pctBig}%</span>
                                    <span className="text-gray-500 text-xl font-medium">({stats.big})</span>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

// --- MAIN APP COMPONENT ---
const ConsistencyApp = () => {
    const [data, setData] = React.useState([]);
    const [loading, setLoading] = React.useState(true);
    const [selectedReq, setSelectedReq] = React.useState(null);
    const [statusFilter, setStatusFilter] = React.useState('Status');
    const [sortOption, setSortOption] = React.useState('Ascending');
    const [currentPage, setCurrentPage] = React.useState(1);
    
    const [isStatusOpen, setIsStatusOpen] = React.useState(false);
    const [isSortOpen, setIsSortOpen] = React.useState(false);
    const statusRef = React.useRef(null);
    const sortRef = React.useRef(null);

    // --- DATA FETCHING & TRANSFORMATION ---
    React.useEffect(() => {
        const fetchData = async () => {
            let fetchedData = [];
            let i = 1;
            let keepFetching = true;
            const BASE_PATH = '/static/floorplan_app/module_Survey/';

            while (keepFetching) {
                try {
                    const response = await fetch(`${BASE_PATH}${i}.json`);
                    if (response.ok) {
                        const json = await response.json();
                        
                        let areaDisplay = "N/A";
                        let areaValue = 0; 
                        
                        if (json.total_area) {
                            if (json.total_area.total_area_50 === 1) { areaDisplay = "50 ~ 100"; areaValue = 50; }
                            else if (json.total_area.total_area_100 === 1) { areaDisplay = "100 ~ 150"; areaValue = 100; }
                            else if (json.total_area.total_area_150 === 1) { areaDisplay = "150 ~ 200"; areaValue = 150; }
                            else if (json.total_area.total_area_200 === 1) { areaDisplay = "200 ~ 250"; areaValue = 200; }
                        }

                        const summaryItems = [];
                        const checkError = (constKey) => {
                            if (!json.room_consistency || !json.room_consistency[constKey]) return false;
                            const c = json.room_consistency[constKey];
                            if (c.good == 1) return false;
                            if (c.too_small == 0 && c.good == 0 && c.too_big == 0) return false;
                            if (c.too_small == 1 || c.too_big == 1) return true;
                            return false;
                        };

                        const getCount = (roomKey) => json.rooms ? (json.rooms[roomKey] || 0) : 0;

                        // -- LDK --
                        let ldkCount = 0;
                        for(let k=1; k<=4; k++) { if(getCount(`bedroom_${k}`) === 1) ldkCount = k; }
                        summaryItems.push({ label: 'LDK', count: ldkCount, isError: checkError('ldk') });
                        // -- Japan --
                        summaryItems.push({ label: 'Japan Style Room', count: getCount('japan'), isError: checkError('japan') });
                        // -- Study --
                        summaryItems.push({ label: 'Study Room', count: getCount('study'), isError: checkError('study') });
                        // -- Storage --
                        summaryItems.push({ label: 'Storage Room', count: getCount('storage'), isError: checkError('storage') });
                        // -- Balcony --
                        summaryItems.push({ label: 'Balcony', count: getCount('balcony'), isError: checkError('balcony') });
                        // -- Toilet --
                        let toiletCount = 0;
                        let toiletError = false;
                        for(let k=1; k<=4; k++) { 
                            if(getCount(`toilet_${k}`) === 1) toiletCount = k; 
                            if (checkError(`toilet_${k}`)) toiletError = true;
                        }
                        summaryItems.push({ label: 'Toilet', count: toiletCount, isError: toiletError });

                        const transformed = {
                            ...json,
                            _fileIndex: i,
                            isSuccess: json.Consistency === true,
                            request_id: json.processing_times && json.processing_times[0]?.req_id 
                                        ? `REQ_${json.processing_times[0].req_id}` 
                                        : `FILE_${i}`,
                            area: areaDisplay, 
                            areaValue: areaValue,
                            summaryItems: summaryItems,
                            errorCount: summaryItems.filter(x => x.isError).length 
                        };

                        fetchedData.push(transformed);
                        i++;
                    } else {
                        keepFetching = false;
                    }
                } catch (e) {
                    keepFetching = false;
                }
            }
            setData(fetchedData);
            setLoading(false);
        };
        fetchData();
    }, []);

    // Outside click handler
    React.useEffect(() => {
        function handleClickOutside(event) {
            if (statusRef.current && !statusRef.current.contains(event.target)) setIsStatusOpen(false);
            if (sortRef.current && !sortRef.current.contains(event.target)) setIsSortOpen(false);
        }
        document.addEventListener("mousedown", handleClickOutside);
        return () => document.removeEventListener("mousedown", handleClickOutside);
    }, []);

    // --- LOGIC ---
    const totalRequests = data.length;
    const totalSuccess = data.filter(r => r.isSuccess).length;
    const totalFailed = data.filter(r => !r.isSuccess).length;

    // Filter & Sort Logic (UPDATED)
    const processedData = React.useMemo(() => {
        let processed = [...data];
        
        // 1. Status Filter
        if (statusFilter === 'Success') processed = processed.filter(r => r.isSuccess);
        else if (statusFilter === 'Failed') processed = processed.filter(r => !r.isSuccess);

        // 2. Sort Logic based on Status
        // Rule: If Filter is 'Failed' -> Sort by Error Count (Lỗi)
        // Rule: If Filter is 'All' OR 'Success' -> Sort by Area Value (Diện tích)
        const useErrorLogic = (statusFilter === 'Failed');

        if (sortOption === 'Ascending') {
            if (useErrorLogic) {
                 // Sort by Error Count: Low -> High
                 processed.sort((a, b) => a.errorCount - b.errorCount);
            } else {
                 // Sort by Area: Low -> High
                 processed.sort((a, b) => a.areaValue - b.areaValue);
            }
        } else if (sortOption === 'Descending') {
            if (useErrorLogic) {
                // Sort by Error Count: High -> Low
                processed.sort((a, b) => b.errorCount - a.errorCount);
            } else {
                // Sort by Area: High -> Low
                processed.sort((a, b) => b.areaValue - a.areaValue);
            }
        } else if (sortOption === 'Largest') {
            if (useErrorLogic) {
                // Filter Max Error Count
                if (processed.length > 0) {
                    const maxErr = Math.max(...processed.map(i => i.errorCount));
                    processed = processed.filter(i => i.errorCount === maxErr);
                }
            } else {
                // Filter Max Area
                if (processed.length > 0) {
                    const maxArea = Math.max(...processed.map(i => i.areaValue));
                    processed = processed.filter(i => i.areaValue === maxArea);
                }
            }
        } else if (sortOption === 'Smallest') {
            if (useErrorLogic) {
                // Filter Min Error Count
                if (processed.length > 0) {
                    const minErr = Math.min(...processed.map(i => i.errorCount));
                    processed = processed.filter(i => i.errorCount === minErr);
                }
            } else {
                // Filter Min Area
                if (processed.length > 0) {
                    const minArea = Math.min(...processed.map(i => i.areaValue));
                    processed = processed.filter(i => i.areaValue === minArea);
                }
            }
        }

        return processed;
    }, [data, statusFilter, sortOption]);

    // Pagination
    const itemsPerPage = 7;
    const totalPages = Math.ceil(processedData.length / itemsPerPage);
    const currentItems = processedData.slice((currentPage - 1) * itemsPerPage, currentPage * itemsPerPage);

    const handlePageChange = (newPage) => {
        if (newPage >= 1 && newPage <= totalPages) setCurrentPage(newPage);
    };

    if (loading) return <div className="p-10 text-center text-gray-500">Loading Data...</div>;

    return (
        <div className="p-6 sm:p-10 bg-gray-50 min-h-screen font-sans">
            <div className="flex justify-between items-end mb-10">
                <h1 className="text-3xl font-bold text-gray-900 tracking-tight">Consistency</h1>
            </div>

            {/* TOP STATS */}
            <div className="w-full mx-auto mb-10 grid grid-cols-1 md:grid-cols-3 gap-8">
                <div className="bg-blue-600 rounded-2xl p-6 flex items-center shadow-lg shadow-blue-200">
                    <div className="w-16 h-16 bg-blue-700 rounded-xl flex items-center justify-center text-white mr-6 flex-shrink-0">
                        <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"></path><rect x="8" y="2" width="8" height="4" rx="1" ry="1"></rect><path d="M9 14h6"></path><path d="M12 11v6"></path></svg>
                    </div>
                    <div className="flex flex-col items-center">
                        <span className="text-blue-100 text-sm font-bold uppercase tracking-wide">Total Request</span>
                        <div className="text-white text-4xl font-extrabold mt-2">{totalRequests}</div>
                    </div>
                </div>
                <div className="bg-green-50 border border-green-100 rounded-2xl p-6 flex items-center shadow-sm">
                    <div className="w-16 h-16 bg-green-200 rounded-xl flex items-center justify-center text-green-600 mr-6 flex-shrink-0">
                        <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>
                    </div>
                    <div className="flex flex-col items-center">
                        <span className="text-green-500 text-sm font-bold uppercase tracking-wide">Total Success</span>
                        <div className="text-green-900 text-4xl font-extrabold mt-2">{totalSuccess}</div>
                    </div>
                </div>
                <div className="bg-gray-100 border border-gray-200 rounded-2xl p-6 flex items-center shadow-sm">
                    <div className="w-16 h-16 bg-gray-200 rounded-xl flex items-center justify-center text-gray-500 mr-6 flex-shrink-0">
                        <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
                    </div>
                    <div className="flex flex-col items-center">
                        <span className="text-gray-500 text-sm font-bold uppercase tracking-wide">Total Failed</span>
                        <div className="text-gray-900 text-4xl font-extrabold mt-2">{totalFailed}</div>
                    </div>
                </div>
            </div>

            {/* MAIN CONTENT GRID */}
            <div className="w-full mx-auto grid grid-cols-1 lg:grid-cols-5 gap-8 h-[800px]">
                {/* LEFT: ANALYSIS CARD */}
                <div className="col-span-1 lg:col-span-2 h-full">
                    <BedroomAnalysisCard data={data} selectedReq={selectedReq} onBack={() => setSelectedReq(null)} />
                </div>

                {/* RIGHT: TABLE */}
                <div className="col-span-1 lg:col-span-3 bg-white rounded-xl shadow-sm border border-gray-200 pb-6 flex flex-col h-full">
                    <div className="flex justify-between items-center px-8 py-8 border-b border-gray-100 flex-shrink-0">
                        <h1 className="text-2xl font-bold text-gray-800 uppercase tracking-wide">PROCESS REQUESTS</h1>
                        <div className="flex gap-4">
                            {/* Filter Dropdown */}
                            <div className="relative dropdown-menu-container" ref={statusRef}>
                                <button onClick={() => setIsStatusOpen(!isStatusOpen)} className={`flex items-center justify-between gap-3 px-5 py-3 bg-white border rounded-lg text-base hover:bg-gray-50 min-w-[140px] transition-colors font-medium ${statusFilter !== 'Status' ? 'border-blue-500 text-blue-600' : 'border-gray-200 text-gray-600'}`}>
                                    {statusFilter} <ChevronDown size={18} className={`transition-transform ${isStatusOpen ? 'rotate-180' : ''}`} />
                                </button>
                                {isStatusOpen && (
                                    <div className="absolute top-full mt-2 right-0 w-40 bg-white border border-gray-200 rounded-lg shadow-lg py-2">
                                        {['All', 'Success', 'Failed'].map(opt => (
                                            <button key={opt} onClick={() => { setStatusFilter(opt); setIsStatusOpen(false); setCurrentPage(1); }} className="w-full text-left px-5 py-3 text-base hover:bg-gray-50 text-gray-700">{opt}</button>
                                        ))}
                                    </div>
                                )}
                            </div>
                            {/* Sort Dropdown */}
                            <div className="relative dropdown-menu-container" ref={sortRef}>
                                <button onClick={() => setIsSortOpen(!isSortOpen)} className="flex items-center justify-between gap-3 px-5 py-3 bg-white border border-gray-200 rounded-lg text-base text-gray-600 hover:bg-gray-50 min-w-[150px] font-medium">
                                    {sortOption} <ChevronDown size={18} className={`transition-transform ${isSortOpen ? 'rotate-180' : ''}`} />
                                </button>
                                {isSortOpen && (
                                    <div className="absolute top-full mt-2 right-0 w-48 bg-white border border-gray-200 rounded-lg shadow-lg py-2">
                                        {['Ascending', 'Descending', 'Largest', 'Smallest'].map(opt => (
                                            <button key={opt} onClick={() => { setSortOption(opt); setIsSortOpen(false); }} className="w-full text-left px-5 py-3 text-base hover:bg-gray-50 text-gray-700">{opt}</button>
                                        ))}
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>

                    <div className="overflow-x-auto flex-grow px-2 custom-scrollbar overflow-y-auto">
                        <table className="w-full text-left border-collapse">
                            <thead className="sticky top-0 bg-white z-10">
                                <tr className="border-b border-gray-200 text-sm font-bold text-gray-900 uppercase tracking-wider bg-gray-50/50">
                                    <th className="px-6 py-6 w-20 text-center">STT</th>
                                    <th className="px-6 py-6 w-32 text-center">ID</th>
                                    <th className="px-6 py-6">INPUT SUMMARY</th>
                                    <th className="px-6 py-6 w-32 text-center">Area (m²)</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-50">
                                {currentItems.length > 0 ? (
                                    currentItems.map((row, idx) => {
                                        const globalIndex = (currentPage - 1) * itemsPerPage + idx + 1;
                                        return (
                                            <tr key={idx} className="hover:bg-gray-50/80 transition-colors group">
                                                <td className="px-6 py-8 text-center text-gray-600 font-medium text-lg">{globalIndex}</td>
                                                <td className="px-6 py-8 text-center">
                                                    <button onClick={() => setSelectedReq(row)} className={`${row.isSuccess ? 'bg-blue-600 hover:bg-blue-700' : 'bg-red-500 hover:bg-red-600'} text-white text-sm font-bold px-4 py-2 rounded shadow-sm inline-block min-w-[100px] transition-colors`}>
                                                        {row.request_id}
                                                    </button>
                                                </td>
                                                <td className="px-6 py-8">
                                                    <div className="flex flex-wrap gap-2">
                                                        {row.summaryItems.map((item, i) => (
                                                            <span key={i} className={`px-2 py-1 rounded text-xs font-medium ${item.isError ? 'badge-error' : 'badge-default'}`}>
                                                                {item.count} {item.label}
                                                            </span>
                                                        ))}
                                                    </div>
                                                </td>
                                                <td className="px-6 py-8 text-center font-bold text-gray-700">
                                                    {row.area}
                                                </td>
                                            </tr>
                                        );
                                    })
                                ) : (
                                    <tr><td colSpan="4" className="px-8 py-12 text-center text-gray-500 text-lg">No requests found matching your filter.</td></tr>
                                )}
                            </tbody>
                        </table>
                    </div>

                    <div className="flex justify-end items-center px-8 py-6 gap-6 text-gray-500 text-sm mt-2 border-t border-gray-50 flex-shrink-0">
                        <button disabled={currentPage === 1} onClick={() => handlePageChange(currentPage - 1)} className="disabled:opacity-30 hover:text-gray-800 transition-colors"><ChevronLeft size={24} /></button>
                        <span className="font-semibold text-base">Page {currentPage} of {totalPages || 1}</span>
                        <button disabled={currentPage === totalPages || totalPages === 0} onClick={() => handlePageChange(currentPage + 1)} className="disabled:opacity-30 hover:text-gray-800 transition-colors"><ChevronRight size={24} /></button>
                    </div>
                </div>
            </div>
        </div>
    );
};

// MOUNT APP
const root = ReactDOM.createRoot(document.getElementById('react-consistency-root'));
root.render(<ConsistencyApp />);