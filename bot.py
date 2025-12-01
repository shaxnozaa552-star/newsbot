import logging
import asyncio
import random
import time
from datetime import time as dtime
from typing import Dict, List, Set
from dataclasses import dataclass

import feedparser
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ========== КОНФИГУРАЦИЯ ==========
TELEGRAM_BOT_TOKEN = "8532133326:AAHXXzVWhx8NAIE_ZCn7x45yO24F_QDMWds"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# ========== МОДЕЛИ ДАННЫХ ==========
@dataclass
class NewsArticle:
    id: str
    title: str
    link: str
    category: str
    source: str
    timestamp: float

class NewsBot:
    def __init__(self):
        self.subscribers: Dict[int, Set[str]] = {}
        self.news_cache: Dict[str, float] = {}
        
        self.CATEGORIES = {
            "политика": [
                "https://lenta.ru/rss",
                "https://ria.ru/export/rss2/politics.xml",
                "https://www.vedomosti.ru/rss/news"
            ],
            "экономика": [
                "https://www.vedomosti.ru/rss/news",
                "https://ria.ru/export/rss2/economy.xml",
                "https://www.kommersant.ru/RSS/news.xml"
            ],
            "технологии": [
                "https://habr.com/ru/rss/hub/python/",
                "https://vc.ru/rss",
                "https://3dnews.ru/news/rss/"
            ],
            "спорт": [
                "https://www.championat.com/rss/news.xml",
                "https://www.sports.ru/rss/rubric.xml?s=208",
                "https://rsport.ria.ru/export/rss2/index.xml"
            ],
            "культура": [
                "https://www.kp.ru/rss/theme/10/",
                "https://www.kommersant.ru/RSS/section-culture.xml",
                "https://rg.ru/rss/culture.xml"
            ],
        }

    # ========== КЛАВИАТУРЫ ==========
    def get_start_menu(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([[
            InlineKeyboardButton("🚀 Начать работу", callback_data="start_work")
        ]])

    def get_categories_keyboard(self, selected: Set[str] = None) -> InlineKeyboardMarkup:
        selected = selected or set()
        keyboard = [
            [InlineKeyboardButton(
                f"{'✅' if category in selected else '⚪'} {category}", 
                callback_data=f"cat_{category}"
            )] for category in self.CATEGORIES
        ]
        keyboard.append([InlineKeyboardButton("💾 Сохранить", callback_data="save_cats")])
        return InlineKeyboardMarkup(keyboard)

    def get_main_menu(self) -> InlineKeyboardMarkup:
        buttons = [
            [InlineKeyboardButton("📰 Получить новости", callback_data="get_news")],
            [InlineKeyboardButton("⚙️ Категории", callback_data="change_cats")],
        ]
        return InlineKeyboardMarkup(buttons)

    # ========== ЛОГИКА НОВОСТЕЙ ==========
    def _parse_feed(self, feed_url: str, category: str) -> List[NewsArticle]:
        """Парсит RSS фид и возвращает список новостей."""
        try:
            feed = feedparser.parse(feed_url)
            articles = []
            
            for entry in feed.entries[:8]:  # Берем больше для разнообразия
                title = entry.title[:77] + "..." if len(entry.title) > 80 else entry.title
                news_id = f"{category}_{hash(title) % 10000}"
                
                articles.append(NewsArticle(
                    id=news_id,
                    title=title,
                    link=entry.link,
                    category=category,
                    source=feed_url.split('/')[2],
                    timestamp=time.time()
                ))
            
            return articles
        except Exception as e:
            logging.error(f"Ошибка парсинга {feed_url}: {e}")
            return []

    def fetch_fresh_news(self, categories: List[str]) -> str:
        """Генерирует свежие новости для выбранных категорий."""
        if not categories:
            return "❌ Выберите категории в настройках"

        all_articles = []
        
        for category in categories:
            if category not in self.CATEGORIES:
                continue
                
            # Случайный выбор источника для разнообразия
            feed_url = random.choice(self.CATEGORIES[category])
            articles = self._parse_feed(feed_url, category)
            all_articles.extend(articles)

        if not all_articles:
            return "❌ Новости не найдены"

        # Убираем дубликаты и выбираем случайные 5 новостей
        unique_articles = {article.id: article for article in all_articles}
        selected_articles = random.sample(
            list(unique_articles.values()), 
            min(5, len(unique_articles))
        )

        # Форматируем ответ
        news_text = f"📰 <b>Свежие новости ({', '.join(categories)}):</b>\n\n"
        for i, article in enumerate(selected_articles, 1):
            news_text += (
                f"<b>{i}. {article.title}</b>\n"
                f"🏷️ {article.category} | 📡 {article.source}\n"
                f"<a href='{article.link}'>📖 Читать далее</a>\n\n"
            )

        return news_text

    # ========== ОБРАБОТЧИКИ ==========
    async def handle_buttons(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает нажатия inline-кнопок."""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        data = query.data

        handlers = {
            'start_work': self._handle_start,
            'save_cats': self._handle_save_cats,
            'get_news': self._handle_get_news,
            'change_cats': self._handle_change_cats,
        }
        
        if data.startswith('cat_'):
            await self._handle_category_select(query, user_id, data)
        elif data in handlers:
            await handlers[data](query, user_id)

    async def _handle_start(self, query, user_id):
        await query.edit_message_text(
            "📋 Выберите категории новостей:",
            reply_markup=self.get_categories_keyboard(),
        )

    async def _handle_category_select(self, query, user_id, data):
        category = data.replace("cat_", "")
        
        if user_id not in self.subscribers:
            self.subscribers[user_id] = set()
        
        user_cats = self.subscribers[user_id]
        if category in user_cats:
            user_cats.remove(category)
        else:
            user_cats.add(category)

        await query.edit_message_reply_markup(
            reply_markup=self.get_categories_keyboard(user_cats)
        )

    async def _handle_save_cats(self, query, user_id):
        if user_id in self.subscribers and self.subscribers[user_id]:
            cats = self.subscribers[user_id]
            await query.edit_message_text(
                "✅ Подписка оформлена!\n\n"
                f"📋 Категории: {', '.join(cats)}\n\n"
                "⏰ Рассылка в 09:00 и 18:00\n\n"
                "📱 Главное меню:",
                reply_markup=self.get_main_menu(),
            )
        else:
            await query.edit_message_text(
                "❌ Выберите хотя бы одну категорию!",
                reply_markup=self.get_categories_keyboard(),
            )

    async def _handle_get_news(self, query, user_id):
        cats = list(self.subscribers.get(user_id, {"политика"}))
        await query.edit_message_text("🔄 Загружаю свежие новости...")
        
        news_text = self.fetch_fresh_news(cats)
        
        await query.message.reply_text(news_text, parse_mode="HTML")
        await query.message.reply_text(
            "🔄 Нажмите 'Получить новости' для следующих новостей!\n\n"
            "📱 Меню:",
            reply_markup=self.get_main_menu()
        )

    async def _handle_change_cats(self, query, user_id):
        current_cats = self.subscribers.get(user_id, set())
        await query.edit_message_text(
            "📋 Изменить категории:",
            reply_markup=self.get_categories_keyboard(current_cats),
        )

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "👋 Добро пожаловать в NewsBot!\n\n"
            "📰 Ваш персональный агрегатор новостей.\n"
            "🔄 Каждый раз новые свежие новости!",
            reply_markup=self.get_start_menu(),
        )

    async def news(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_chat.id
        cats = list(self.subscribers.get(user_id, {"политика"}))
        await update.message.reply_text("🔄 Загружаю свежие новости...")
        
        news_text = self.fetch_fresh_news(cats)
        
        await update.message.reply_text(news_text, parse_mode="HTML")
        await update.message.reply_text(
            "🔄 Используйте /news для следующих новостей!\n\n"
            "📱 Меню:",
            reply_markup=self.get_main_menu()
        )

    async def send_news_to_all(self, context: ContextTypes.DEFAULT_TYPE):
        """Рассылка новостей всем подписчикам."""
        if not self.subscribers:
            return

        for user_id, categories in self.subscribers.items():
            news_text = self.fetch_fresh_news(list(categories))
            try:
                await context.bot.send_message(
                    chat_id=user_id, 
                    text=news_text, 
                    parse_mode="HTML"
                )
            except Exception as e:
                logging.warning(f"Не удалось отправить пользователю {user_id}: {e}")

# ========== ЗАПУСК ПРИЛОЖЕНИЯ ==========
def main():
    bot = NewsBot()
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Регистрация обработчиков
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("news", bot.news))
    application.add_handler(CallbackQueryHandler(bot.handle_buttons))

    # Настройка планировщика
    if application.job_queue:
        application.job_queue.run_daily(
            bot.send_news_to_all,
            time=dtime(hour=9, minute=0),
            name="morning_news",
        )
        application.job_queue.run_daily(
            bot.send_news_to_all,
            time=dtime(hour=18, minute=0),
            name="evening_news",
        )
        logging.info("✅ Планировщик рассылки настроен")

    # Запуск бота
    logging.info("🚀 Бот запущен!")
    application.run_polling()

if __name__ == "__main__":
    main()
