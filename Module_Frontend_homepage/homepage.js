        // 1. Initialize Icons
        lucide.createIcons();

        // 2. Navbar Scroll Effect
        window.addEventListener('scroll', () => {
            const nav = document.getElementById('navbar');
            if (window.scrollY > 20) {
                nav.classList.add('bg-white/80', 'backdrop-blur-md', 'border-b', 'border-neutral-200');
                nav.classList.remove('bg-transparent', 'border-transparent');
            } else {
                nav.classList.remove('bg-white/80', 'backdrop-blur-md', 'border-b', 'border-neutral-200');
                nav.classList.add('bg-transparent', 'border-transparent');
            }
        });

        // 3. Mobile Menu Toggle
        const menuBtn = document.getElementById('mobile-menu-btn');
        const mobileMenu = document.getElementById('mobile-menu');
        menuBtn.addEventListener('click', () => {
            mobileMenu.classList.toggle('hidden');
            const icon = mobileMenu.classList.contains('hidden') ? 'menu' : 'x';
            // Re-render icon logic if needed, or simple toggle
        });

        // 4. Marquee Content Injection
        const roomLayouts = [
            { name: "Master Bedroom", img: "{% static 'floorplan_app/images/homepage/master_bedroom.png' %}" },
            { name: "Home Office 1", img: "{% static 'floorplan_app/images/homepage/home_office_01.png' %}" },
            { name: "Home Office 2", img: "{% static 'floorplan_app/images/homepage/home_office_02.png' %}" },
            { name: "Entertainment Unit 1", img: "{% static 'floorplan_app/images/homepage/entertainment_unit_01.png' %}" },
            { name: "Entertainment Unit 2", img: "{% static 'floorplan_app/images/homepage/entertainment_unit_02.png' %}" },
            { name: "Entertainment Unit 3", img: "{% static 'floorplan_app/images/homepage/entertainment_unit_03.png' %}" },
            { name: "Laundry Room", img: "{% static 'floorplan_app/images/homepage/laundry_room.png' %}" },
            { name: "Shower Room 1", img: "{% static 'floorplan_app/images/homepage/shower_room_01.png' %}" },
            { name: "Shower Room 2", img: "{% static 'floorplan_app/images/homepage/shower_room_02.png' %}" },
            { name: "Bathtub Suite 1", img: "{% static 'floorplan_app/images/homepage/bathtub_suite_01.png' %}" },
            { name: "Bathtub Suite 2", img: "{% static 'floorplan_app/images/homepage/bathtub_suite_02.png' %}" },
            { name: "Dining Area 1", img: "{% static 'floorplan_app/images/homepage/dining_area_01.png' %}" },
            { name: "Dining Area 2", img: "{% static 'floorplan_app/images/homepage/dining_area_02.png' %}" },
            { name: "Large Wardrobe 1", img: "{% static 'floorplan_app/images/homepage/large_wardrobe_01.png' %}" },
            { name: "Large Wardrobe 2", img: "{% static 'floorplan_app/images/homepage/large_wardrobe_02.png' %}" },
            { name: "Large Wardrobe 3", img: "{% static 'floorplan_app/images/homepage/large_wardrobe_03.png' %}" }
        ];

        function createMarqueeItem(room) {
            // Đã cập nhật class img: Xóa grayscale và opacity, giữ lại drop-shadow và object-contain
            return `
            <div class="w-[300px] md:w-[400px] flex-shrink-0 group">
                <div class="rounded-2xl border border-neutral-200 overflow-hidden bg-neutral-50 shadow-sm transition-all duration-300 group-hover:shadow-lg group-hover:border-neutral-300 relative aspect-square">
                    <div class="absolute inset-0 bg-neutral-50 flex items-center justify-center p-8">
                        <img src="${room.img}" alt="${room.name}" class="w-full h-full object-contain transition-all duration-500 drop-shadow-xl">
                    </div>
                </div>
                <h4 class="mt-4 text-center font-medium text-neutral-600 group-hover:text-black transition-colors">${room.name}</h4>
            </div>`;
        }

        const marqueeContent = document.getElementById('marquee-content');
        const marqueeClone = document.getElementById('marquee-content-clone');
        
        const htmlContent = roomLayouts.map(createMarqueeItem).join('');
        marqueeContent.innerHTML = htmlContent;
        marqueeClone.innerHTML = htmlContent;

        // 5. Pricing Toggle Logic
        let isAnnual = true;
        function setPricing(type) {
            const btnMonthly = document.getElementById('btn-monthly');
            const btnYearly = document.getElementById('btn-yearly');
            const pricePro = document.getElementById('price-plus'); // Fixed ID reference
            const periodPro = document.getElementById('period-plus'); // Fixed ID reference

            const activeClass = "bg-white text-black shadow-sm ring-1 ring-black/5";
            const inactiveClass = "text-neutral-500 hover:text-black bg-transparent shadow-none ring-0";

            if (type === 'yearly') {
                isAnnual = true;
                btnYearly.className = `px-6 py-2 rounded-full text-sm font-medium transition-all ${activeClass}`;
                btnMonthly.className = `px-6 py-2 rounded-full text-sm font-medium transition-all ${inactiveClass}`;
                if(pricePro) pricePro.innerText = "$290";
                if(periodPro) periodPro.innerText = "/year";
            } else {
                isAnnual = false;
                btnMonthly.className = `px-6 py-2 rounded-full text-sm font-medium transition-all ${activeClass}`;
                btnYearly.className = `px-6 py-2 rounded-full text-sm font-medium transition-all ${inactiveClass}`;
                if(pricePro) pricePro.innerText = "$29";
                if(periodPro) periodPro.innerText = "/month";
            }
        }

        // 6. FAQ Accordion Logic
        function toggleFaq(button) {
            const content = button.nextElementSibling;
            const icon = button.querySelector('[data-lucide="chevron-down"]');
            
            // Toggle current
            if (content.style.maxHeight && content.style.maxHeight !== '0px') {
                content.style.maxHeight = '0px';
                content.style.opacity = '0';
                button.classList.remove('active');
                icon.style.transform = 'rotate(0deg)';
            } else {
                content.style.maxHeight = content.scrollHeight + "px";
                content.style.opacity = '1';
                button.classList.add('active');
                icon.style.transform = 'rotate(180deg)';
            }
        }
