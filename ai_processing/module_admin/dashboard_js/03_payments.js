const PaymentsModule = {
    addCredit: () => {
        const amount = prompt("Nhập số tiền muốn nạp ($):", "100");
        if(amount) alert(`Đang tạo hóa đơn nạp $${amount}`);
    }
};