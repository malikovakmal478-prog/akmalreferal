?<php
/**
 * Telegram Market Bot
 * @Akmaljon1100 tomonidan tarqatilmoqda bu kod 
 *Manbaga tegmang boʻlmasa ishlamaydi kod
 */

// Bot sozlamalari
define('BOT_TOKEN', '8858044044:AAEyMd-XXF4V_23hQKuWzblQwCaONvwKyqg'); // Bot tokeningizni kiriting
define('ADMIN_ID', 7849637859); // Ad id
define('ADMIN_USERNAME', '@Akmaljon1100'); // Admin useri
define('API_URL', 'https://api.telegram.org/bot' . BOT_TOKEN . '/');
define('USERS_FILE', 'data/users.json');
define('PRODUCTS_FILE', 'data/products.json');
define('ORDERS_FILE', 'data/orders.json');
define('CHANNELS_FILE', 'data/channels.json');
define('PAYMENTS_FILE', 'data/payments.json');
define('PROMOCODES_FILE', 'data/promocodes.json');
define('DISCOUNTS_FILE', 'data/discounts.json');
define('TEMP_FILE', 'data/temp.json');

// Papkalarni yaratish
if (!file_exists('data')) mkdir('data', 0777, true);
if (!file_exists('images')) mkdir('images', 0777, true);

// JSON fayllarni yuklash
function loadJson($file) {
    if (!file_exists($file)) {
        file_put_contents($file, json_encode([]));
    }
    return json_decode(file_get_contents($file), true) ?: [];
}

// JSON faylga saqlash
function saveJson($file, $data) {
    file_put_contents($file, json_encode($data, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE));
}

// Telegram API so'rov
function sendRequest($method, $params = []) {
    $ch = curl_init();
    curl_setopt($ch, CURLOPT_URL, API_URL . $method);
    curl_setopt($ch, CURLOPT_POST, true);
    curl_setopt($ch, CURLOPT_POSTFIELDS, $params);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_SSL_VERIFYPEER, false);
    $result = curl_exec($ch);
    curl_close($ch);
    return json_decode($result, true);
}

// Rasmli xabar yuborish
function sendPhoto($chat_id, $photo, $caption = '', $reply_markup = null) {
    $params = [
        'chat_id' => $chat_id,
        'photo' => $photo,
        'caption' => $caption,
        'parse_mode' => 'HTML'
    ];
    if ($reply_markup) {
        $params['reply_markup'] = json_encode($reply_markup);
    }
    return sendRequest('sendPhoto', $params);
}

// Oddiy xabar yuborish
function sendMessage($chat_id, $text, $reply_markup = null) {
    $params = [
        'chat_id' => $chat_id,
        'text' => $text,
        'parse_mode' => 'HTML'
    ];
    if ($reply_markup) {
        $params['reply_markup'] = json_encode($reply_markup);
    }
    return sendRequest('sendMessage', $params);
}

// Xabarni tahrirlash
function editMessage($chat_id, $message_id, $text, $reply_markup = null) {
    $params = [
        'chat_id' => $chat_id,
        'message_id' => $message_id,
        'text' => $text,
        'parse_mode' => 'HTML'
    ];
    if ($reply_markup) {
        $params['reply_markup'] = json_encode($reply_markup);
    }
    return sendRequest('editMessageText', $params);
}

// Callback javob
function answerCallback($callback_id, $text = '', $show_alert = false) {
    return sendRequest('answerCallbackQuery', [
        'callback_query_id' => $callback_id,
        'text' => $text,
        'show_alert' => $show_alert
    ]);
}

// Rasmni yuklab olish
function downloadFile($file_id) {
    $file = sendRequest('getFile', ['file_id' => $file_id]);
    if ($file['ok']) {
        $file_path = $file['result']['file_path'];
        $url = "https://api.telegram.org/file/bot" . BOT_TOKEN . "/" . $file_path;
        $ext = pathinfo($file_path, PATHINFO_EXTENSION);
        $local_path = 'images/' . uniqid() . '.' . $ext;
        file_put_contents($local_path, file_get_contents($url));
        return $local_path;
    }
    return null;
}

// Foydalanuvchini ro'yxatdan o'tkazish
function registerUser($user) {
    $users = loadJson(USERS_FILE);
    $user_id = $user['id'];
    
    if (!isset($users[$user_id])) {
        $users[$user_id] = [
            'id' => $user_id,
            'first_name' => $user['first_name'] ?? '',
            'last_name' => $user['last_name'] ?? '',
            'username' => $user['username'] ?? '',
            'balance' => 0,
            'orders_count' => 0,
            'joined_at' => date('Y-m-d H:i:s'),
            'promocode_used' => false
        ];
        saveJson(USERS_FILE, $users);
    }
    return $users[$user_id];
}

// Admin tekshirish
function isAdmin($user_id) {
    return $user_id == ADMIN_ID;
}

// Majburiy obuna tekshirish
function checkSubscription($user_id) {
    $channels = loadJson(CHANNELS_FILE);
    if (empty($channels)) return true;
    
    foreach ($channels as $channel) {
        $result = sendRequest('getChatMember', [
            'chat_id' => $channel['id'],
            'user_id' => $user_id
        ]);
        if (!$result['ok'] || in_array($result['result']['status'], ['left', 'kicked'])) {
            return false;
        }
    }
    return true;
}

// Asosiy klaviatura
function mainKeyboard($user_id) {
    $keyboard = [
        ['🛒 Market', '👤 Hisobim'],
        ['💳 Pul kiritish', '📦 Buyurtmalarim'],
        ['🏷 Chegirmalar', '📞 Murojaat qilish']
    ];
    
    if (isAdmin($user_id)) {
        $keyboard[] = ['⚙️ Admin panel'];
    }
    
    return ['keyboard' => $keyboard, 'resize_keyboard' => true];
}

// Admin klaviatura
function adminKeyboard() {
    return [
        'keyboard' => [
            ['📊 Statistika', '📦 Buyurtmalar'],
            ['📨 Habar yuborish', '📢 Majburiy obuna'],
            ['🛍 Mahsulot', '💳 Tolov usullari'],
            ['🎟 Promokod', '🔙 Orqaga']
        ],
        'resize_keyboard' => true
    ];
}

// Vaqtinchalik ma'lumot saqlash
function setTemp($user_id, $data) {
    $temp = loadJson(TEMP_FILE);
    $temp[$user_id] = $data;
    saveJson(TEMP_FILE, $temp);
}

// Vaqtinchalik ma'lumot olish
function getTemp($user_id) {
    $temp = loadJson(TEMP_FILE);
    return $temp[$user_id] ?? null;
}

// Vaqtinchalik ma'lumotni o'chirish
function clearTemp($user_id) {
    $temp = loadJson(TEMP_FILE);
    unset($temp[$user_id]);
    saveJson(TEMP_FILE, $temp);
}

// ==================== ASOSIY BOT LOGIKASI ====================

$update = json_decode(file_get_contents('php://input'), true);

if (!$update) exit;

// Message handler
if (isset($update['message'])) {
    $message = $update['message'];
    $chat_id = $message['chat']['id'];
    $user_id = $message['from']['id'];
    $text = $message['text'] ?? '';
    $photo = $message['photo'] ?? null;
    
    // Foydalanuvchini ro'yxatdan o'tkazish
    $user = registerUser($message['from']);
    
    // Majburiy obuna tekshirish
    if (!checkSubscription($user_id) && $text != '/start') {
        $channels = loadJson(CHANNELS_FILE);
        $buttons = [];
        foreach ($channels as $channel) {
            $buttons[] = [['text' => '📢 ' . $channel['name'], 'url' => $channel['url']]];
        }
        $buttons[] = [['text' => '✅ Tekshirish', 'callback_data' => 'check_sub']];
        
        sendPhoto($chat_id, 
            'https://i.imgur.com/subscription.png',
            "⚠️ <b>Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:</b>",
            ['inline_keyboard' => $buttons]
        );
        exit;
    }
    
    // Vaqtinchalik holat tekshirish
    $temp = getTemp($user_id);
    
    // Rasm kelsa
    if ($photo && $temp) {
        handlePhotoMessage($chat_id, $user_id, $photo, $temp);
        exit;
    }
    
    // Matn kelsa va holat mavjud
    if ($temp && $text) {
        handleTempState($chat_id, $user_id, $text, $temp);
        exit;
    }
    
    // /start buyrug'i
    if ($text == '/start') {
        sendPhoto($chat_id,
            'https://i.imgur.com/market_welcome.png',
            "🎉 <b>Xush kelibsiz!</b>\n\n" .
            "🛒 Bu bot orqali siz turli mahsulotlarni sotib olishingiz mumkin.\n\n" .
            "📦 Bizning afzalliklarimiz:\n" .
            "• Tezkor yetkazib berish\n" .
            "• Sifatli mahsulotlar\n" .
            "• Qulay narxlar\n" .
            "• 24/7 qo'llab-quvvatlash\n\n" .
            "⬇️ Quyidagi tugmalardan birini tanlang:",
            mainKeyboard($user_id)
        );
        exit;
    }
    
    // 🛒 Market
    if ($text == '🛒 Market') {
        showMarket($chat_id, $user_id);
        exit;
    }
    
    // 👤 Hisobim
    if ($text == '👤 Hisobim') {
        showAccount($chat_id, $user_id, $user);
        exit;
    }
    
    // 💳 Pul kiritish
    if ($text == '💳 Pul kiritish') {
        showPaymentMethods($chat_id, $user_id);
        exit;
    }
    
    // 📦 Buyurtmalarim
    if ($text == '📦 Buyurtmalarim') {
        showMyOrders($chat_id, $user_id);
        exit;
    }
    
    // 🏷 Chegirmalar
    if ($text == '🏷 Chegirmalar') {
        showDiscounts($chat_id, $user_id);
        exit;
    }
    
    // 📞 Murojaat qilish
    if ($text == '📞 Murojaat qilish') {
        sendPhoto($chat_id,
            'https://i.imgur.com/contact.png',
            "📞 <b>Biz bilan bog'lanish</b>\n\n" .
            "Savollaringiz bo'lsa, quyidagi tugma orqali admin bilan bog'laning:\n\n" .
            "⏰ Ish vaqti: 09:00 - 22:00",
            ['inline_keyboard' => [
                [['text' => '👨‍💼 Admin bilan bog\'lanish', 'url' => 'https://t.me/' . str_replace('@', '', ADMIN_USERNAME)]]
            ]]
        );
        exit;
    }
    
    // ⚙️ Admin panel
    if ($text == '⚙️ Admin panel' && isAdmin($user_id)) {
        sendPhoto($chat_id,
            'https://i.imgur.com/admin_panel.png',
            "⚙️ <b>Admin Panel</b>\n\n" .
            "Quyidagi bo'limlardan birini tanlang:",
            adminKeyboard()
        );
        exit;
    }
    
    // 🔙 Orqaga
    if ($text == '🔙 Orqaga') {
        sendPhoto($chat_id,
            'https://i.imgur.com/main_menu.png',
            "🏠 <b>Asosiy menyu</b>\n\nQuyidagi tugmalardan birini tanlang:",
            mainKeyboard($user_id)
        );
        exit;
    }
    
    // ==================== ADMIN PANEL ====================
    
    if (isAdmin($user_id)) {
        // 📊 Statistika
        if ($text == '📊 Statistika') {
            showStatistics($chat_id);
            exit;
        }
        
        // 📦 Buyurtmalar
        if ($text == '📦 Buyurtmalar') {
            showAllOrders($chat_id);
            exit;
        }
        
        // 📨 Habar yuborish
        if ($text == '📨 Habar yuborish') {
            setTemp($user_id, ['action' => 'broadcast']);
            sendPhoto($chat_id,
                'https://i.imgur.com/broadcast.png',
                "📨 <b>Habar yuborish</b>\n\n" .
                "Barcha foydalanuvchilarga yuboriladigan xabarni kiriting:\n\n" .
                "❌ Bekor qilish uchun /cancel buyrug'ini yuboring",
                ['inline_keyboard' => [[['text' => '❌ Bekor qilish', 'callback_data' => 'cancel_action']]]]
            );
            exit;
        }
        
        // 📢 Majburiy obuna
        if ($text == '📢 Majburiy obuna') {
            showChannels($chat_id);
            exit;
        }
        
        // 🛍 Mahsulot
        if ($text == '🛍 Mahsulot') {
            sendPhoto($chat_id,
                'https://i.imgur.com/products.png',
                "🛍 <b>Mahsulotlar boshqaruvi</b>\n\nQuyidagi amallardan birini tanlang:",
                ['inline_keyboard' => [
                    [['text' => '➕ Mahsulot qo\'shish', 'callback_data' => 'add_product']],
                    [['text' => '🗑 Mahsulotni o\'chirish', 'callback_data' => 'delete_product']],
                    [['text' => '📋 Barcha mahsulotlar', 'callback_data' => 'all_products']]
                ]]
            );
            exit;
        }
        
        // 💳 Tolov usullari
        if ($text == '💳 Tolov usullari') {
            showPaymentSettings($chat_id);
            exit;
        }
        
        // 🎟 Promokod
        if ($text == '🎟 Promokod') {
            showPromocodes($chat_id);
            exit;
        }
    }
    
    // /cancel buyrug'i
    if ($text == '/cancel') {
        clearTemp($user_id);
        sendMessage($chat_id, "❌ Amal bekor qilindi.", mainKeyboard($user_id));
        exit;
    }
}

// Callback handler
if (isset($update['callback_query'])) {
    $callback = $update['callback_query'];
    $chat_id = $callback['message']['chat']['id'];
    $user_id = $callback['from']['id'];
    $message_id = $callback['message']['message_id'];
    $data = $callback['data'];
    
    answerCallback($callback['id']);
    
    // Obuna tekshirish
    if ($data == 'check_sub') {
        if (checkSubscription($user_id)) {
            sendMessage($chat_id, "✅ Obuna tasdiqlandi! Endi botdan foydalanishingiz mumkin.", mainKeyboard($user_id));
        } else {
            answerCallback($callback['id'], "❌ Siz hali obuna bo'lmagansiz!", true);
        }
        exit;
    }
    
    // Bekor qilish
    if ($data == 'cancel_action') {
        clearTemp($user_id);
        editMessage($chat_id, $message_id, "❌ Amal bekor qilindi.");
        exit;
    }
    
    // Market qidirish
    if ($data == 'search_market') {
        setTemp($user_id, ['action' => 'search_product']);
        editMessage($chat_id, $message_id, 
            "🔍 <b>Mahsulot qidirish</b>\n\nMahsulot nomini yozing:",
            ['inline_keyboard' => [[['text' => '❌ Bekor qilish', 'callback_data' => 'cancel_action']]]]
        );
        exit;
    }
    
    // Rasm bilan qidirish
    if ($data == 'search_by_image') {
        setTemp($user_id, ['action' => 'search_by_image']);
        editMessage($chat_id, $message_id,
            "📷 <b>Rasm bilan qidirish</b>\n\nMahsulot rasmini yuboring:",
            ['inline_keyboard' => [[['text' => '❌ Bekor qilish', 'callback_data' => 'cancel_action']]]]
        );
        exit;
    }
    
    // Mahsulotni ko'rish
    if (strpos($data, 'view_product_') === 0) {
        $product_id = str_replace('view_product_', '', $data);
        showProduct($chat_id, $user_id, $product_id);
        exit;
    }
    
    // Mahsulotni sotib olish
    if (strpos($data, 'buy_product_') === 0) {
        $product_id = str_replace('buy_product_', '', $data);
        buyProduct($chat_id, $user_id, $product_id);
        exit;
    }
    
    // Promokod kiritish
    if ($data == 'enter_promocode') {
        setTemp($user_id, ['action' => 'enter_promocode']);
        sendMessage($chat_id, 
            "🎟 <b>Promokod kiritish</b>\n\nPromokodni kiriting:",
            ['inline_keyboard' => [[['text' => '❌ Bekor qilish', 'callback_data' => 'cancel_action']]]]
        );
        exit;
    }
    
    // To'lov usulini tanlash
    if (strpos($data, 'pay_method_') === 0) {
        $method = str_replace('pay_method_', '', $data);
        setTemp($user_id, ['action' => 'enter_amount', 'method' => $method]);
        sendMessage($chat_id,
            "💰 <b>Pul miqdorini kiriting</b>\n\nQancha pul kiritmoqchisiz? (so'm)",
            ['inline_keyboard' => [[['text' => '❌ Bekor qilish', 'callback_data' => 'cancel_action']]]]
        );
        exit;
    }
    
    // ==================== ADMIN CALLBACKS ====================
    
    if (isAdmin($user_id)) {
        // Mahsulot qo'shish
        if ($data == 'add_product') {
            setTemp($user_id, ['action' => 'add_product_images', 'images' => []]);
            sendMessage($chat_id,
                "📷 <b>Mahsulot qo'shish</b>\n\n" .
                "Mahsulot uchun rasmlarni yuboring (kamida 3 ta).\n" .
                "Rasmlarni yuborib bo'lgach, <b>Tayyor</b> tugmasini bosing.",
                ['inline_keyboard' => [
                    [['text' => '✅ Tayyor', 'callback_data' => 'images_done']],
                    [['text' => '❌ Bekor qilish', 'callback_data' => 'cancel_action']]
                ]]
            );
            exit;
        }
        
        // Rasmlar tayyor
        if ($data == 'images_done') {
            $temp = getTemp($user_id);
            if ($temp && isset($temp['images']) && count($temp['images']) >= 3) {
                $temp['action'] = 'add_product_name';
                setTemp($user_id, $temp);
                sendMessage($chat_id,
                    "✅ Rasmlar qabul qilindi!\n\n📝 Endi mahsulot nomini kiriting:",
                    ['inline_keyboard' => [[['text' => '❌ Bekor qilish', 'callback_data' => 'cancel_action']]]]
                );
            } else {
                answerCallback($callback['id'], "❌ Kamida 3 ta rasm kerak!", true);
            }
            exit;
        }
        
        // Mahsulotni marketga qo'shish
        if ($data == 'product_to_market') {
            $temp = getTemp($user_id);
            if ($temp) {
                $products = loadJson(PRODUCTS_FILE);
                $product_id = uniqid();
                $products[$product_id] = [
                    'id' => $product_id,
                    'name' => $temp['name'],
                    'description' => $temp['description'],
                    'price' => $temp['price'],
                    'images' => $temp['images'],
                    'discount' => 0,
                    'category' => 'market',
                    'created_at' => date('Y-m-d H:i:s')
                ];
                saveJson(PRODUCTS_FILE, $products);
                clearTemp($user_id);
                
                sendPhoto($chat_id,
                    'https://i.imgur.com/success.png',
                    "✅ <b>Mahsulot muvaffaqiyatli qo'shildi!</b>\n\n" .
                    "📦 Nomi: {$temp['name']}\n" .
                    "💰 Narxi: {$temp['price']} so'm",
                    adminKeyboard()
                );
            }
            exit;
        }
        
        // Mahsulotni chegirmaga qo'shish
        if ($data == 'product_to_discount') {
            $temp = getTemp($user_id);
            if ($temp) {
                $temp['action'] = 'add_discount_percent';
                setTemp($user_id, $temp);
                sendMessage($chat_id,
                    "🏷 <b>Chegirma foizini kiriting</b>\n\nNecha foiz chegirma qilmoqchisiz? (1-99)",
                    ['inline_keyboard' => [[['text' => '❌ Bekor qilish', 'callback_data' => 'cancel_action']]]]
                );
            }
            exit;
        }
        
        // Mahsulotni o'chirish
        if ($data == 'delete_product') {
            $products = loadJson(PRODUCTS_FILE);
            if (empty($products)) {
                answerCallback($callback['id'], "❌ Mahsulotlar mavjud emas!", true);
                exit;
            }
            
            $buttons = [];
            foreach ($products as $id => $product) {
                $buttons[] = [['text' => '🗑 ' . $product['name'], 'callback_data' => 'del_prod_' . $id]];
            }
            $buttons[] = [['text' => '🔙 Orqaga', 'callback_data' => 'back_to_products']];
            
            editMessage($chat_id, $message_id,
                "🗑 <b>O'chiriladigan mahsulotni tanlang:</b>",
                ['inline_keyboard' => $buttons]
            );
            exit;
        }
        
        // Mahsulotni o'chirish tasdiqlash
        if (strpos($data, 'del_prod_') === 0) {
            $product_id = str_replace('del_prod_', '', $data);
            $products = loadJson(PRODUCTS_FILE);
            if (isset($products[$product_id])) {
                $name = $products[$product_id]['name'];
                unset($products[$product_id]);
                saveJson(PRODUCTS_FILE, $products);
                editMessage($chat_id, $message_id, "✅ <b>$name</b> mahsuloti o'chirildi!");
            }
            exit;
        }
        
        // Barcha mahsulotlar
        if ($data == 'all_products') {
            $products = loadJson(PRODUCTS_FILE);
            if (empty($products)) {
                answerCallback($callback['id'], "❌ Mahsulotlar mavjud emas!", true);
                exit;
            }
            
            $text = "📋 <b>Barcha mahsulotlar:</b>\n\n";
            $i = 1;
            foreach ($products as $product) {
                $discount_text = $product['discount'] > 0 ? " (-{$product['discount']}%)" : "";
                $text .= "$i. {$product['name']} - {$product['price']} so'm$discount_text\n";
                $i++;
            }
            
            editMessage($chat_id, $message_id, $text,
                ['inline_keyboard' => [[['text' => '🔙 Orqaga', 'callback_data' => 'back_to_products']]]]
            );
            exit;
        }
        
        // Mahsulotlar menyusiga qaytish
        if ($data == 'back_to_products') {
            editMessage($chat_id, $message_id,
                "🛍 <b>Mahsulotlar boshqaruvi</b>\n\nQuyidagi amallardan birini tanlang:",
                ['inline_keyboard' => [
                    [['text' => '➕ Mahsulot qo\'shish', 'callback_data' => 'add_product']],
                    [['text' => '🗑 Mahsulotni o\'chirish', 'callback_data' => 'delete_product']],
                    [['text' => '📋 Barcha mahsulotlar', 'callback_data' => 'all_products']]
                ]]
            );
            exit;
        }
        
        // Kanal qo'shish
        if ($data == 'add_channel') {
            setTemp($user_id, ['action' => 'add_channel_id']);
            sendMessage($chat_id,
                "📢 <b>Kanal qo'shish</b>\n\nKanal ID raqamini kiriting (masalan: -1001234567890):",
                ['inline_keyboard' => [[['text' => '❌ Bekor qilish', 'callback_data' => 'cancel_action']]]]
            );
            exit;
        }
        
        // Kanalni o'chirish
        if (strpos($data, 'del_channel_') === 0) {
            $channel_id = str_replace('del_channel_', '', $data);
            $channels = loadJson(CHANNELS_FILE);
            unset($channels[$channel_id]);
            saveJson(CHANNELS_FILE, $channels);
            showChannels($chat_id);
            exit;
        }
        
        // To'lov usuli qo'shish
        if ($data == 'add_payment') {
            setTemp($user_id, ['action' => 'add_payment_name']);
            sendMessage($chat_id,
                "💳 <b>To'lov usuli qo'shish</b>\n\nTo'lov usuli nomini kiriting (masalan: Click, Payme):",
                ['inline_keyboard' => [[['text' => '❌ Bekor qilish', 'callback_data' => 'cancel_action']]]]
            );
            exit;
        }
        
        // To'lov usulini o'chirish
        if (strpos($data, 'del_payment_') === 0) {
            $payment_id = str_replace('del_payment_', '', $data);
            $payments = loadJson(PAYMENTS_FILE);
            unset($payments[$payment_id]);
            saveJson(PAYMENTS_FILE, $payments);
            showPaymentSettings($chat_id);
            exit;
        }
        
        // Promokod qo'shish
        if ($data == 'add_promocode') {
            setTemp($user_id, ['action' => 'add_promo_code']);
            sendMessage($chat_id,
                "🎟 <b>Promokod qo'shish</b>\n\nPromokod nomini kiriting:",
                ['inline_keyboard' => [[['text' => '❌ Bekor qilish', 'callback_data' => 'cancel_action']]]]
            );
            exit;
        }
        
        // Promokodni o'chirish
        if (strpos($data, 'del_promo_') === 0) {
            $promo_id = str_replace('del_promo_', '', $data);
            $promocodes = loadJson(PROMOCODES_FILE);
            unset($promocodes[$promo_id]);
            saveJson(PROMOCODES_FILE, $promocodes);
            showPromocodes($chat_id);
            exit;
        }
        
        // Buyurtmani tasdiqlash
        if (strpos($data, 'confirm_order_') === 0) {
            $order_id = str_replace('confirm_order_', '', $data);
            $orders = loadJson(ORDERS_FILE);
            if (isset($orders[$order_id])) {
                $orders[$order_id]['status'] = 'confirmed';
                saveJson(ORDERS_FILE, $orders);
                
                // Foydalanuvchiga xabar
                sendMessage($orders[$order_id]['user_id'],
                    "✅ <b>Buyurtmangiz tasdiqlandi!</b>\n\n" .
                    "📦 Buyurtma: #{$order_id}\n" .
                    "Tez orada siz bilan bog'lanamiz."
                );
                
                editMessage($chat_id, $message_id, "✅ Buyurtma #{$order_id} tasdiqlandi!");
            }
            exit;
        }
        
        // Buyurtmani bekor qilish
        if (strpos($data, 'reject_order_') === 0) {
            $order_id = str_replace('reject_order_', '', $data);
            $orders = loadJson(ORDERS_FILE);
            if (isset($orders[$order_id])) {
                $orders[$order_id]['status'] = 'rejected';
                saveJson(ORDERS_FILE, $orders);
                
                // Foydalanuvchiga xabar
                sendMessage($orders[$order_id]['user_id'],
                    "❌ <b>Buyurtmangiz bekor qilindi!</b>\n\n" .
                    "📦 Buyurtma: #{$order_id}\n" .
                    "Iltimos, admin bilan bog'laning."
                );
                
                editMessage($chat_id, $message_id, "❌ Buyurtma #{$order_id} bekor qilindi!");
            }
            exit;
        }
        
        // To'lovni tasdiqlash
        if (strpos($data, 'confirm_pay_') === 0) {
            $pay_id = str_replace('confirm_pay_', '', $data);
            $temp = loadJson(TEMP_FILE);
            if (isset($temp['pending_payments'][$pay_id])) {
                $payment = $temp['pending_payments'][$pay_id];
                $users = loadJson(USERS_FILE);
                $users[$payment['user_id']]['balance'] += $payment['amount'];
                saveJson(USERS_FILE, $users);
                
                unset($temp['pending_payments'][$pay_id]);
                saveJson(TEMP_FILE, $temp);
                
                sendMessage($payment['user_id'],
                    "✅ <b>To'lov tasdiqlandi!</b>\n\n" .
                    "💰 Miqdor: {$payment['amount']} so'm\n" .
                    "💳 Hisobingizga qo'shildi!"
                );
                
                editMessage($chat_id, $message_id, "✅ To'lov tasdiqlandi!");
            }
            exit;
        }
        
        // To'lovni rad etish
        if (strpos($data, 'reject_pay_') === 0) {
            $pay_id = str_replace('reject_pay_', '', $data);
            $temp = loadJson(TEMP_FILE);
            if (isset($temp['pending_payments'][$pay_id])) {
                $payment = $temp['pending_payments'][$pay_id];
                
                sendMessage($payment['user_id'],
                    "❌ <b>To'lov rad etildi!</b>\n\n" .
                    "Iltimos, admin bilan bog'laning."
                );
                
                unset($temp['pending_payments'][$pay_id]);
                saveJson(TEMP_FILE, $temp);
                
                editMessage($chat_id, $message_id, "❌ To'lov rad etildi!");
            }
            exit;
        }
    }
    
    // Market sahifalarini ko'rish
    if (strpos($data, 'market_page_') === 0) {
        $page = (int)str_replace('market_page_', '', $data);
        showMarketPage($chat_id, $message_id, $page);
        exit;
    }
    
    // Orqaga (market)
    if ($data == 'back_to_market') {
        showMarketPage($chat_id, $message_id, 1);
        exit;
    }
}

// ==================== FUNKSIYALAR ====================

// Market ko'rsatish
function showMarket($chat_id, $user_id) {
    $products = loadJson(PRODUCTS_FILE);
    
    sendPhoto($chat_id,
        'https://i.imgur.com/market.png',
        "🛒 <b>Market</b>\n\nMahsulotlar ro'yxati va qidiruv:",
        ['inline_keyboard' => [
            [['text' => '🔍 Qidirish', 'callback_data' => 'search_market'], ['text' => '📷 Rasm bilan qidirish', 'callback_data' => 'search_by_image']]
        ]]
    );
    
    if (empty($products)) {
        sendMessage($chat_id, "😔 Hozircha mahsulotlar mavjud emas.");
        return;
    }
    
    // Eng yangi mahsulotlarni ko'rsatish
    $recent = array_slice($products, -5, 5, true);
    $recent = array_reverse($recent, true);
    
    foreach ($recent as $id => $product) {
        $price = number_format($product['price'], 0, '', ' ');
        $discount_text = '';
        if ($product['discount'] > 0) {
            $old_price = $product['price'];
            $new_price = $product['price'] * (100 - $product['discount']) / 100;
            $price = "<s>" . number_format($old_price, 0, '', ' ') . "</s> " . number_format($new_price, 0, '', ' ');
            $discount_text = "🏷 <b>-{$product['discount']}% chegirma!</b>\n";
        }
        
        $photo = !empty($product['images']) ? (file_exists($product['images'][0]) ? new CURLFile($product['images'][0]) : $product['images'][0]) : 'https://i.imgur.com/product.png';
        
        sendPhoto($chat_id, $photo,
            "📦 <b>{$product['name']}</b>\n\n" .
            $discount_text .
            "💰 Narxi: $price so'm\n\n" .
            $product['description'],
            ['inline_keyboard' => [
                [['text' => '🛒 Sotib olish', 'callback_data' => 'buy_product_' . $id]],
                [['text' => '📋 Batafsil', 'callback_data' => 'view_product_' . $id]]
            ]]
        );
    }
}

// Market sahifasi
function showMarketPage($chat_id, $message_id, $page) {
    $products = loadJson(PRODUCTS_FILE);
    $per_page = 5;
    $total = count($products);
    $pages = ceil($total / $per_page);
    
    $offset = ($page - 1) * $per_page;
    $items = array_slice($products, $offset, $per_page, true);
    
    $text = "🛒 <b>Market</b> (Sahifa $page/$pages)\n\n";
    
    $buttons = [];
    foreach ($items as $id => $product) {
        $price = number_format($product['price'], 0, '', ' ');
        if ($product['discount'] > 0) {
            $new_price = $product['price'] * (100 - $product['discount']) / 100;
            $price = number_format($new_price, 0, '', ' ') . " (-{$product['discount']}%)";
        }
        $text .= "📦 {$product['name']} - $price so'm\n";
        $buttons[] = [['text' => $product['name'], 'callback_data' => 'view_product_' . $id]];
    }
    
    $nav = [];
    if ($page > 1) {
        $nav[] = ['text' => '⬅️ Oldingi', 'callback_data' => 'market_page_' . ($page - 1)];
    }
    if ($page < $pages) {
        $nav[] = ['text' => '➡️ Keyingi', 'callback_data' => 'market_page_' . ($page + 1)];
    }
    if (!empty($nav)) {
        $buttons[] = $nav;
    }
    
    editMessage($chat_id, $message_id, $text, ['inline_keyboard' => $buttons]);
}

// Mahsulotni ko'rsatish
function showProduct($chat_id, $user_id, $product_id) {
    $products = loadJson(PRODUCTS_FILE);
    if (!isset($products[$product_id])) {
        sendMessage($chat_id, "❌ Mahsulot topilmadi.");
        return;
    }
    
    $product = $products[$product_id];
    $price = number_format($product['price'], 0, '', ' ');
    $discount_text = '';
    
    if ($product['discount'] > 0) {
        $new_price = $product['price'] * (100 - $product['discount']) / 100;
        $discount_text = "🏷 <b>Chegirma: -{$product['discount']}%</b>\n";
        $price = "<s>" . number_format($product['price'], 0, '', ' ') . "</s> " . number_format($new_price, 0, '', ' ');
    }
    
    // Barcha rasmlarni yuborish
    if (!empty($product['images'])) {
        $media = [];
        foreach ($product['images'] as $i => $image) {
            $media[] = [
                'type' => 'photo',
                'media' => file_exists($image) ? new CURLFile($image) : $image,
                'caption' => $i === 0 ? 
                    "📦 <b>{$product['name']}</b>\n\n" .
                    $discount_text .
                    "💰 Narxi: $price so'm\n\n" .
                    "📝 {$product['description']}" : '',
                'parse_mode' => 'HTML'
            ];
        }
        
        // Bitta rasm yuborish
        $photo = file_exists($product['images'][0]) ? new CURLFile($product['images'][0]) : $product['images'][0];
        sendPhoto($chat_id, $photo,
            "📦 <b>{$product['name']}</b>\n\n" .
            $discount_text .
            "💰 Narxi: $price so'm\n\n" .
            "📝 {$product['description']}",
            ['inline_keyboard' => [
                [['text' => '🛒 Sotib olish', 'callback_data' => 'buy_product_' . $product_id]],
                [['text' => '🔙 Orqaga', 'callback_data' => 'back_to_market']]
            ]]
        );
    }
}

// Mahsulot sotib olish
function buyProduct($chat_id, $user_id, $product_id) {
    $products = loadJson(PRODUCTS_FILE);
    $users = loadJson(USERS_FILE);
    
    if (!isset($products[$product_id])) {
        sendMessage($chat_id, "❌ Mahsulot topilmadi.");
        return;
    }
    
    $product = $products[$product_id];
    $price = $product['price'];
    
    if ($product['discount'] > 0) {
        $price = $price * (100 - $product['discount']) / 100;
    }
    
    // Foydalanuvchi balansini tekshirish
    $user = $users[$user_id] ?? null;
    if (!$user || $user['balance'] < $price) {
        sendPhoto($chat_id,
            'https://i.imgur.com/no_balance.png',
            "❌ <b>Hisobingizda yetarli mablag' yo'q!</b>\n\n" .
            "💰 Kerakli summa: " . number_format($price, 0, '', ' ') . " so'm\n" .
            "💳 Hisobingiz: " . number_format($user['balance'] ?? 0, 0, '', ' ') . " so'm\n\n" .
            "Iltimos, hisobingizni to'ldiring.",
            ['inline_keyboard' => [[['text' => '💳 Pul kiritish', 'callback_data' => 'add_balance']]]]
        );
        return;
    }
    
    // Balansdan yechish
    $users[$user_id]['balance'] -= $price;
    $users[$user_id]['orders_count']++;
    saveJson(USERS_FILE, $users);
    
    // Buyurtma yaratish
    $orders = loadJson(ORDERS_FILE);
    $order_id = uniqid();
    $orders[$order_id] = [
        'id' => $order_id,
        'user_id' => $user_id,
        'product_id' => $product_id,
        'product_name' => $product['name'],
        'price' => $price,
        'status' => 'pending',
        'created_at' => date('Y-m-d H:i:s')
    ];
    saveJson(ORDERS_FILE, $orders);
    
    // Foydalanuvchiga xabar
    sendPhoto($chat_id,
        'https://i.imgur.com/order_success.png',
        "✅ <b>Buyurtma muvaffaqiyatli yaratildi!</b>\n\n" .
        "📦 Mahsulot: {$product['name']}\n" .
        "💰 Narxi: " . number_format($price, 0, '', ' ') . " so'm\n" .
        "🆔 Buyurtma raqami: #{$order_id}\n\n" .
        "Tez orada siz bilan bog'lanamiz!"
    );
    
    // Adminga xabar
    $user_info = "👤 Foydalanuvchi: " . ($users[$user_id]['first_name'] ?? '') . "\n";
    $user_info .= "🆔 User ID: $user_id\n";
    $user_info .= "📞 Username: @" . ($users[$user_id]['username'] ?? 'yo\'q');
    
    sendMessage(ADMIN_ID,
        "🆕 <b>Yangi buyurtma!</b>\n\n" .
        "📦 Mahsulot: {$product['name']}\n" .
        "💰 Narxi: " . number_format($price, 0, '', ' ') . " so'm\n" .
        "🆔 Buyurtma: #{$order_id}\n\n" .
        $user_info,
        ['inline_keyboard' => [
            [['text' => '✅ Tasdiqlash', 'callback_data' => 'confirm_order_' . $order_id]],
            [['text' => '❌ Bekor qilish', 'callback_data' => 'reject_order_' . $order_id]]
        ]]
    );
}

// Hisobim
function showAccount($chat_id, $user_id, $user) {
    $balance = number_format($user['balance'] ?? 0, 0, '', ' ');
    $orders = $user['orders_count'] ?? 0;
    
    sendPhoto($chat_id,
        'https://i.imgur.com/account.png',
        "👤 <b>Mening hisobim</b>\n\n" .
        "🆔 Telegram ID: <code>$user_id</code>\n" .
        "📅 Ro'yxatdan o'tgan: {$user['joined_at']}\n" .
        "💰 Balans: $balance so'm\n" .
        "📦 Buyurtmalar soni: $orders ta\n",
        ['inline_keyboard' => [
            [['text' => '🎟 Promokod kiritish', 'callback_data' => 'enter_promocode']]
        ]]
    );
}

// To'lov usullari
function showPaymentMethods($chat_id, $user_id) {
    $payments = loadJson(PAYMENTS_FILE);
    
    if (empty($payments)) {
        sendPhoto($chat_id,
            'https://i.imgur.com/payment.png',
            "💳 <b>Pul kiritish</b>\n\n" .
            "❌ Hozircha to'lov usullari mavjud emas.\n" .
            "Iltimos, keyinroq urinib ko'ring."
        );
        return;
    }
    
    $buttons = [];
    foreach ($payments as $id => $payment) {
        $buttons[] = [['text' => $payment['name'], 'callback_data' => 'pay_method_' . $id]];
    }
    
    sendPhoto($chat_id,
        'https://i.imgur.com/payment.png',
        "💳 <b>Pul kiritish</b>\n\nTo'lov usulini tanlang:",
        ['inline_keyboard' => $buttons]
    );
}

// Buyurtmalarim
function showMyOrders($chat_id, $user_id) {
    $orders = loadJson(ORDERS_FILE);
    $user_orders = array_filter($orders, fn($o) => $o['user_id'] == $user_id);
    
    if (empty($user_orders)) {
        sendPhoto($chat_id,
            'https://i.imgur.com/no_orders.png',
            "📦 <b>Buyurtmalarim</b>\n\n" .
            "😔 Sizda hali buyurtmalar mavjud emas.\n" .
            "Market bo'limidan mahsulot sotib oling!"
        );
        return;
    }
    
    $text = "📦 <b>Mening buyurtmalarim:</b>\n\n";
    foreach ($user_orders as $order) {
        $status_emoji = match($order['status']) {
            'pending' => '⏳',
            'confirmed' => '✅',
            'rejected' => '❌',
            default => '📦'
        };
        $status_text = match($order['status']) {
            'pending' => 'Kutilmoqda',
            'confirmed' => 'Tasdiqlangan',
            'rejected' => 'Bekor qilingan',
            default => 'Noma\'lum'
        };
        
        $text .= "$status_emoji #{$order['id']}\n";
        $text .= "📦 {$order['product_name']}\n";
        $text .= "💰 " . number_format($order['price'], 0, '', ' ') . " so'm\n";
        $text .= "📋 Holat: $status_text\n";
        $text .= "📅 {$order['created_at']}\n\n";
    }
    
    sendPhoto($chat_id,
        'https://i.imgur.com/orders.png',
        $text
    );
}

// Chegirmalar
function showDiscounts($chat_id, $user_id) {
    $products = loadJson(PRODUCTS_FILE);
    $discounted = array_filter($products, fn($p) => $p['discount'] > 0);
    
    if (empty($discounted)) {
        sendPhoto($chat_id,
            'https://i.imgur.com/no_discounts.png',
            "🏷 <b>Chegirmalar</b>\n\n" .
            "😔 Hozircha chegirmadagi mahsulotlar mavjud emas.\n" .
            "Tez orada yangi chegirmalar qo'shiladi!"
        );
        return;
    }
    
    sendPhoto($chat_id,
        'https://i.imgur.com/discounts.png',
        "🏷 <b>Chegirmadagi mahsulotlar</b>\n\nQuyidagi mahsulotlarda chegirma mavjud:"
    );
    
    foreach ($discounted as $id => $product) {
        $old_price = number_format($product['price'], 0, '', ' ');
        $new_price = number_format($product['price'] * (100 - $product['discount']) / 100, 0, '', ' ');
        
        $photo = !empty($product['images']) ? (file_exists($product['images'][0]) ? new CURLFile($product['images'][0]) : $product['images'][0]) : 'https://i.imgur.com/product.png';
        
        sendPhoto($chat_id, $photo,
            "📦 <b>{$product['name']}</b>\n\n" .
            "🏷 <b>-{$product['discount']}% chegirma!</b>\n" .
            "💰 Narxi: <s>$old_price</s> $new_price so'm\n\n" .
            $product['description'],
            ['inline_keyboard' => [
                [['text' => '🛒 Sotib olish', 'callback_data' => 'buy_product_' . $id]]
            ]]
        );
    }
}

// Admin: Statistika
function showStatistics($chat_id) {
    $users = loadJson(USERS_FILE);
    $products = loadJson(PRODUCTS_FILE);
    $orders = loadJson(ORDERS_FILE);
    
    $total_users = count($users);
    $total_products = count($products);
    $total_orders = count($orders);
    $pending_orders = count(array_filter($orders, fn($o) => $o['status'] == 'pending'));
    $total_revenue = array_sum(array_column(array_filter($orders, fn($o) => $o['status'] == 'confirmed'), 'price'));
    
    // Bugungi statistika
    $today = date('Y-m-d');
    $today_users = count(array_filter($users, fn($u) => strpos($u['joined_at'], $today) === 0));
    $today_orders = count(array_filter($orders, fn($o) => strpos($o['created_at'], $today) === 0));
    
    sendPhoto($chat_id,
        'https://i.imgur.com/statistics.png',
        "📊 <b>Statistika</b>\n\n" .
        "👥 <b>Foydalanuvchilar:</b>\n" .
        "├ Jami: $total_users ta\n" .
        "└ Bugun: $today_users ta\n\n" .
        "📦 <b>Mahsulotlar:</b> $total_products ta\n\n" .
        "🛒 <b>Buyurtmalar:</b>\n" .
        "├ Jami: $total_orders ta\n" .
        "├ Kutilmoqda: $pending_orders ta\n" .
        "└ Bugun: $today_orders ta\n\n" .
        "💰 <b>Daromad:</b> " . number_format($total_revenue, 0, '', ' ') . " so'm"
    );
}

// Admin: Barcha buyurtmalar
function showAllOrders($chat_id) {
    $orders = loadJson(ORDERS_FILE);
    
    if (empty($orders)) {
        sendPhoto($chat_id,
            'https://i.imgur.com/no_orders.png',
            "📦 <b>Buyurtmalar</b>\n\nHozircha buyurtmalar mavjud emas."
        );
        return;
    }
    
    $pending = array_filter($orders, fn($o) => $o['status'] == 'pending');
    
    if (empty($pending)) {
        sendPhoto($chat_id,
            'https://i.imgur.com/orders.png',
            "📦 <b>Buyurtmalar</b>\n\n✅ Kutilayotgan buyurtmalar yo'q."
        );
        return;
    }
    
    foreach ($pending as $order) {
        $users = loadJson(USERS_FILE);
        $user = $users[$order['user_id']] ?? [];
        
        sendMessage($chat_id,
            "🆕 <b>Buyurtma #{$order['id']}</b>\n\n" .
            "📦 Mahsulot: {$order['product_name']}\n" .
            "💰 Narxi: " . number_format($order['price'], 0, '', ' ') . " so'm\n" .
            "👤 Foydalanuvchi: " . ($user['first_name'] ?? 'Noma\'lum') . "\n" .
            "🆔 User ID: {$order['user_id']}\n" .
            "📅 Sana: {$order['created_at']}",
            ['inline_keyboard' => [
                [['text' => '✅ Tasdiqlash', 'callback_data' => 'confirm_order_' . $order['id']]],
                [['text' => '❌ Bekor qilish', 'callback_data' => 'reject_order_' . $order['id']]]
            ]]
        );
    }
}

// Admin: Kanallar
function showChannels($chat_id) {
    $channels = loadJson(CHANNELS_FILE);
    
    $text = "📢 <b>Majburiy obuna kanallari</b>\n\n";
    
    if (empty($channels)) {
        $text .= "Hozircha kanallar qo'shilmagan.";
    } else {
        foreach ($channels as $id => $channel) {
            $text .= "📢 {$channel['name']}\n";
        }
    }
    
    $buttons = [[['text' => '➕ Kanal qo\'shish', 'callback_data' => 'add_channel']]];
    
    if (!empty($channels)) {
        foreach ($channels as $id => $channel) {
            $buttons[] = [['text' => '🗑 ' . $channel['name'], 'callback_data' => 'del_channel_' . $id]];
        }
    }
    
    sendPhoto($chat_id,
        'https://i.imgur.com/channels.png',
        $text,
        ['inline_keyboard' => $buttons]
    );
}

// Admin: To'lov sozlamalari
function showPaymentSettings($chat_id) {
    $payments = loadJson(PAYMENTS_FILE);
    
    $text = "💳 <b>To'lov usullari</b>\n\n";
    
    if (empty($payments)) {
        $text .= "Hozircha to'lov usullari qo'shilmagan.";
    } else {
        foreach ($payments as $payment) {
            $text .= "💳 {$payment['name']}: {$payment['details']}\n";
        }
    }
    
    $buttons = [[['text' => '➕ To\'lov usuli qo\'shish', 'callback_data' => 'add_payment']]];
    
    if (!empty($payments)) {
        foreach ($payments as $id => $payment) {
            $buttons[] = [['text' => '🗑 ' . $payment['name'], 'callback_data' => 'del_payment_' . $id]];
        }
    }
    
    sendPhoto($chat_id,
        'https://i.imgur.com/payment_settings.png',
        $text,
        ['inline_keyboard' => $buttons]
    );
}

// Admin: Promokodlar
function showPromocodes($chat_id) {
    $promocodes = loadJson(PROMOCODES_FILE);
    
    $text = "🎟 <b>Promokodlar</b>\n\n";
    
    if (empty($promocodes)) {
        $text .= "Hozircha promokodlar qo'shilmagan.";
    } else {
        foreach ($promocodes as $promo) {
            $text .= "🎟 <code>{$promo['code']}</code> - {$promo['discount']}% chegirma\n";
        }
    }
    
    $buttons = [[['text' => '➕ Promokod qo\'shish', 'callback_data' => 'add_promocode']]];
    
    if (!empty($promocodes)) {
        foreach ($promocodes as $id => $promo) {
            $buttons[] = [['text' => '🗑 ' . $promo['code'], 'callback_data' => 'del_promo_' . $id]];
        }
    }
    
    sendPhoto($chat_id,
        'https://i.imgur.com/promocodes.png',
        $text,
        ['inline_keyboard' => $buttons]
    );
}

// Rasm xabarlarni qayta ishlash
function handlePhotoMessage($chat_id, $user_id, $photo, $temp) {
    $file_id = end($photo)['file_id'];
    
    // Mahsulot rasmlarini qo'shish
    if ($temp['action'] == 'add_product_images') {
        $local_path = downloadFile($file_id);
        if ($local_path) {
            $temp['images'][] = $local_path;
            setTemp($user_id, $temp);
            $count = count($temp['images']);
            sendMessage($chat_id,
                "✅ Rasm qabul qilindi! ($count ta)\n\n" .
                ($count < 3 ? "Yana " . (3 - $count) . " ta rasm kerak." : "Tayyor tugmasini bosishingiz mumkin."),
                ['inline_keyboard' => [
                    [['text' => '✅ Tayyor', 'callback_data' => 'images_done']],
                    [['text' => '❌ Bekor qilish', 'callback_data' => 'cancel_action']]
                ]]
            );
        }
        return;
    }
    
    // Rasm bilan qidirish
    if ($temp['action'] == 'search_by_image') {
        clearTemp($user_id);
        $local_path = downloadFile($file_id);
        
        // Rasmlarni solishtirish (oddiy usul)
        $products = loadJson(PRODUCTS_FILE);
        $found = false;
        
        // Bu yerda oddiy fayl hajmi orqali solishtirish
        // Haqiqiy loyihada ML model yoki image hashing ishlatiladi
        foreach ($products as $id => $product) {
            if (!empty($product['images'])) {
                // Soddalik uchun birinchi mahsulotni qaytaramiz
                // Haqiqiy loyihada rasm tanish algoritmi kerak
                $found = true;
                showProduct($chat_id, $user_id, $id);
                break;
            }
        }
        
        if (!$found) {
            sendPhoto($chat_id,
                'https://i.imgur.com/not_found.png',
                "😔 <b>Uzr so'raymiz!</b>\n\n" .
                "Mahsulot rasmini topa olmadik.\n" .
                "Iltimos, rasmni adminga yuboring:",
                ['inline_keyboard' => [
                    [['text' => '👨‍💼 Adminga yuborish', 'url' => 'https://t.me/' . str_replace('@', '', ADMIN_USERNAME)]]
                ]]
            );
        }
        
        if ($local_path && file_exists($local_path)) {
            unlink($local_path);
        }
        return;
    }
    
    // To'lov cheki
    if ($temp['action'] == 'send_receipt') {
        clearTemp($user_id);
        $local_path = downloadFile($file_id);
        
        // Adminga yuborish
        $pay_id = uniqid();
        $temp_data = loadJson(TEMP_FILE);
        $temp_data['pending_payments'][$pay_id] = [
            'user_id' => $user_id,
            'amount' => $temp['amount'],
            'method' => $temp['method'],
            'receipt' => $local_path
        ];
        saveJson(TEMP_FILE, $temp_data);
        
        $users = loadJson(USERS_FILE);
        $user = $users[$user_id] ?? [];
        
        sendPhoto(ADMIN_ID,
            new CURLFile($local_path),
            "💳 <b>Yangi to'lov!</b>\n\n" .
            "💰 Miqdor: {$temp['amount']} so'm\n" .
            "💳 Usul: {$temp['method']}\n" .
            "👤 Foydalanuvchi: " . ($user['first_name'] ?? 'Noma\'lum') . "\n" .
            "🆔 User ID: $user_id",
            ['inline_keyboard' => [
                [['text' => '✅ Tasdiqlash', 'callback_data' => 'confirm_pay_' . $pay_id]],
                [['text' => '❌ Rad etish', 'callback_data' => 'reject_pay_' . $pay_id]]
            ]]
        );
        
        sendPhoto($chat_id,
            'https://i.imgur.com/payment_sent.png',
            "✅ <b>Chek yuborildi!</b>\n\n" .
            "To'lovingiz tekshirilmoqda.\n" .
            "Tasdiqlangach, hisobingizga qo'shiladi."
        );
        return;
    }
}

/**
 * Telegram Market Bot
 * @DavlatyorUz tomonidan tarqatilmoqda bu kod 
 *Manbaga tegmang boʻlmasa ishlamaydi kod
 */
 
// Matnli holatlarni qayta ishlash
function handleTempState($chat_id, $user_id, $text, $temp) {
    // Bekor qilish
    if ($text == '/cancel') {
        clearTemp($user_id);
        sendMessage($chat_id, "❌ Amal bekor qilindi.", mainKeyboard($user_id));
        return;
    }
    
    switch ($temp['action']) {
        // Mahsulot nomi
        case 'add_product_name':
            $temp['name'] = $text;
            $temp['action'] = 'add_product_description';
            setTemp($user_id, $temp);
            sendMessage($chat_id,
                "✅ Nom qabul qilindi!\n\n📝 Endi mahsulot haqida ma'lumot kiriting:",
                ['inline_keyboard' => [[['text' => '❌ Bekor qilish', 'callback_data' => 'cancel_action']]]]
            );
            break;
            
        // Mahsulot tavsifi
        case 'add_product_description':
            $temp['description'] = $text;
            $temp['action'] = 'add_product_price';
            setTemp($user_id, $temp);
            sendMessage($chat_id,
                "✅ Ma'lumot qabul qilindi!\n\n💰 Endi mahsulot narxini kiriting (so'mda):",
                ['inline_keyboard' => [[['text' => '❌ Bekor qilish', 'callback_data' => 'cancel_action']]]]
            );
            break;
            
        // Mahsulot narxi
        case 'add_product_price':
            $price = (int)preg_replace('/[^0-9]/', '', $text);
            if ($price <= 0) {
                sendMessage($chat_id, "❌ Noto'g'ri narx. Iltimos, raqam kiriting.");
                return;
            }
            $temp['price'] = $price;
            $temp['action'] = 'add_product_category';
            setTemp($user_id, $temp);
            
            sendMessage($chat_id,
                "✅ Narx qabul qilindi!\n\n" .
                "📦 Mahsulot: {$temp['name']}\n" .
                "💰 Narxi: " . number_format($price, 0, '', ' ') . " so'm\n\n" .
                "Mahsulotni qayerga qo'shmoqchisiz?",
                ['inline_keyboard' => [
                    [['text' => '🛒 Market', 'callback_data' => 'product_to_market']],
                    [['text' => '🏷 Chegirma', 'callback_data' => 'product_to_discount']]
                ]]
            );
            break;
            
        // Chegirma foizi
        case 'add_discount_percent':
            $discount = (int)$text;
            if ($discount < 1 || $discount > 99) {
                sendMessage($chat_id, "❌ Noto'g'ri foiz. 1 dan 99 gacha raqam kiriting.");
                return;
            }
            
            $products = loadJson(PRODUCTS_FILE);
            $product_id = uniqid();
            $products[$product_id] = [
                'id' => $product_id,
                'name' => $temp['name'],
                'description' => $temp['description'],
                'price' => $temp['price'],
                'images' => $temp['images'],
                'discount' => $discount,
                'category' => 'discount',
                'created_at' => date('Y-m-d H:i:s')
            ];
            saveJson(PRODUCTS_FILE, $products);
            clearTemp($user_id);
            
            $new_price = $temp['price'] * (100 - $discount) / 100;
            
            sendPhoto($chat_id,
                'https://i.imgur.com/success.png',
                "✅ <b>Mahsulot chegirmaga qo'shildi!</b>\n\n" .
                "📦 Nomi: {$temp['name']}\n" .
                "🏷 Chegirma: {$discount}%\n" .
                "💰 Eski narx: " . number_format($temp['price'], 0, '', ' ') . " so'm\n" .
                "💰 Yangi narx: " . number_format($new_price, 0, '', ' ') . " so'm",
                adminKeyboard()
            );
            break;
            
        // Qidiruv
        case 'search_product':
            clearTemp($user_id);
            $products = loadJson(PRODUCTS_FILE);
            $search = mb_strtolower($text);
            
            $found = array_filter($products, function($p) use ($search) {
                return mb_strpos(mb_strtolower($p['name']), $search) !== false ||
                       mb_strpos(mb_strtolower($p['description']), $search) !== false;
            });
            
            if (empty($found)) {
                // O'xshash mahsulotlarni qidirish
                $similar = [];
                foreach ($products as $id => $p) {
                    similar_text(mb_strtolower($p['name']), $search, $percent);
                    if ($percent > 30) {
                        $similar[$id] = $p;
                    }
                }
                
                if (!empty($similar)) {
                    sendMessage($chat_id, "🔍 \"$text\" topilmadi, lekin o'xshash mahsulotlar:");
                    foreach (array_slice($similar, 0, 3, true) as $id => $product) {
                        showProduct($chat_id, $user_id, $id);
                    }
                } else {
                    sendPhoto($chat_id,
                        'https://i.imgur.com/not_found.png',
                        "😔 <b>Mahsulot topilmadi!</b>\n\n" .
                        "\"$text\" bo'yicha hech narsa topilmadi.\n" .
                        "Iltimos, boshqa so'z bilan qidirib ko'ring.",
                        ['inline_keyboard' => [
                            [['text' => '🔍 Qayta qidirish', 'callback_data' => 'search_market']]
                        ]]
                    );
                }
            } else {
                sendMessage($chat_id, "🔍 \"$text\" bo'yicha topildi:");
                foreach ($found as $id => $product) {
                    showProduct($chat_id, $user_id, $id);
                }
            }
            break;
            
        // Promokod kiritish
        case 'enter_promocode':
            clearTemp($user_id);
            $promocodes = loadJson(PROMOCODES_FILE);
            $users = loadJson(USERS_FILE);
            
            $code_found = false;
            foreach ($promocodes as $promo) {
                if (mb_strtoupper($promo['code']) == mb_strtoupper($text)) {
                    $code_found = $promo;
                    break;
                }
            }
            
            if (!$code_found) {
                sendMessage($chat_id, "❌ Noto'g'ri promokod!");
                return;
            }
            
            if ($users[$user_id]['promocode_used']) {
                sendMessage($chat_id, "❌ Siz allaqachon promokoddan foydalangansiz!");
                return;
            }
            
            // Chegirma qo'llash
            $users[$user_id]['promocode_used'] = true;
            $users[$user_id]['discount'] = $code_found['discount'];
            saveJson(USERS_FILE, $users);
            
            sendPhoto($chat_id,
                'https://i.imgur.com/promocode_success.png',
                "🎉 <b>Tabriklaymiz!</b>\n\n" .
                "🎟 Promokod: <code>{$code_found['code']}</code>\n" .
                "🏷 Chegirma: {$code_found['discount']}%\n\n" .
                "Keyingi xaridingizda chegirma qo'llaniladi!"
            );
            break;
            
        // Kanal ID
        case 'add_channel_id':
            $temp['channel_id'] = $text;
            $temp['action'] = 'add_channel_name';
            setTemp($user_id, $temp);
            sendMessage($chat_id,
                "✅ ID qabul qilindi!\n\nKanal nomini kiriting:",
                ['inline_keyboard' => [[['text' => '❌ Bekor qilish', 'callback_data' => 'cancel_action']]]]
            );
            break;
            
        // Kanal nomi
        case 'add_channel_name':
            $temp['channel_name'] = $text;
            $temp['action'] = 'add_channel_url';
            setTemp($user_id, $temp);
            sendMessage($chat_id,
                "✅ Nom qabul qilindi!\n\nKanal linkini kiriting (https://t.me/...):",
                ['inline_keyboard' => [[['text' => '❌ Bekor qilish', 'callback_data' => 'cancel_action']]]]
            );
            break;
            
        // Kanal URL
        case 'add_channel_url':
            $channels = loadJson(CHANNELS_FILE);
            $channel_id = uniqid();
            $channels[$channel_id] = [
                'id' => $temp['channel_id'],
                'name' => $temp['channel_name'],
                'url' => $text
            ];
            saveJson(CHANNELS_FILE, $channels);
            clearTemp($user_id);
            
            sendMessage($chat_id, "✅ Kanal muvaffaqiyatli qo'shildi!", adminKeyboard());
            break;
            
        // To'lov usuli nomi
        case 'add_payment_name':
            $temp['payment_name'] = $text;
            $temp['action'] = 'add_payment_details';
            setTemp($user_id, $temp);
            sendMessage($chat_id,
                "✅ Nom qabul qilindi!\n\nTo'lov ma'lumotlarini kiriting (karta raqami, telefon va h.k.):",
                ['inline_keyboard' => [[['text' => '❌ Bekor qilish', 'callback_data' => 'cancel_action']]]]
            );
            break;
            
        // To'lov usuli ma'lumotlari
        case 'add_payment_details':
            $payments = loadJson(PAYMENTS_FILE);
            $payment_id = uniqid();
            $payments[$payment_id] = [
                'id' => $payment_id,
                'name' => $temp['payment_name'],
                'details' => $text
            ];
            saveJson(PAYMENTS_FILE, $payments);
            clearTemp($user_id);
            
            sendMessage($chat_id, "✅ To'lov usuli muvaffaqiyatli qo'shildi!", adminKeyboard());
            break;
            
        // Promokod
        case 'add_promo_code':
            $temp['promo_code'] = $text;
            $temp['action'] = 'add_promo_discount';
            setTemp($user_id, $temp);
            sendMessage($chat_id,
                "✅ Kod qabul qilindi!\n\nChegirma foizini kiriting (1-99):",
                ['inline_keyboard' => [[['text' => '❌ Bekor qilish', 'callback_data' => 'cancel_action']]]]
            );
            break;
            
        // Promokod foizi
        case 'add_promo_discount':
            $discount = (int)$text;
            if ($discount < 1 || $discount > 99) {
                sendMessage($chat_id, "❌ Noto'g'ri foiz. 1 dan 99 gacha raqam kiriting.");
                return;
            }
            
            $promocodes = loadJson(PROMOCODES_FILE);
            $promo_id = uniqid();
            $promocodes[$promo_id] = [
                'id' => $promo_id,
                'code' => $temp['promo_code'],
                'discount' => $discount
            ];
            saveJson(PROMOCODES_FILE, $promocodes);
            clearTemp($user_id);
            
            sendMessage($chat_id,
                "✅ Promokod qo'shildi!\n\n" .
                "🎟 Kod: <code>{$temp['promo_code']}</code>\n" .
                "🏷 Chegirma: {$discount}%",
                adminKeyboard()
            );
            break;
            
        // Pul miqdori
        case 'enter_amount':
            $amount = (int)preg_replace('/[^0-9]/', '', $text);
            if ($amount < 1000) {
                sendMessage($chat_id, "❌ Minimal summa 1000 so'm!");
                return;
            }
            
            $payments = loadJson(PAYMENTS_FILE);
            $method = $payments[$temp['method']] ?? null;
            
            if (!$method) {
                clearTemp($user_id);
                sendMessage($chat_id, "❌ To'lov usuli topilmadi!");
                return;
            }
            
            $temp['amount'] = $amount;
            $temp['action'] = 'send_receipt';
            setTemp($user_id, $temp);
            
            sendPhoto($chat_id,
                'https://i.imgur.com/payment_info.png',
                "💳 <b>To'lov ma'lumotlari</b>\n\n" .
                "💰 Miqdor: " . number_format($amount, 0, '', ' ') . " so'm\n" .
                "💳 Usul: {$method['name']}\n\n" .
                "📝 <b>To'lov ma'lumotlari:</b>\n{$method['details']}\n\n" .
                "✅ To'lovni amalga oshiring va chekni yuboring:",
                ['inline_keyboard' => [[['text' => '❌ Bekor qilish', 'callback_data' => 'cancel_action']]]]
            );
            break;
            
        // Broadcast
        case 'broadcast':
            clearTemp($user_id);
            $users = loadJson(USERS_FILE);
            $sent = 0;
            $failed = 0;
            
            foreach ($users as $uid => $user) {
                $result = sendMessage($uid, $text);
                if ($result['ok']) {
                    $sent++;
                } else {
                    $failed++;
                }
                usleep(50000); // 50ms kutish
            }
            
            sendPhoto($chat_id,
                'https://i.imgur.com/broadcast_done.png',
                "✅ <b>Xabar yuborildi!</b>\n\n" .
                "📨 Yuborildi: $sent ta\n" .
                "❌ Xatolik: $failed ta",
                adminKeyboard()
            );
            break;
    }
}
/**
 * Telegram Market Bot
 * @DavlatyorUz tomonidan tarqatilmoqda bu kod 
 *Manbaga tegmang boʻlmasa ishlamaydi kod
 */
 
?>
