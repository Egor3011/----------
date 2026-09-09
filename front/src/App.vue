<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'

const activeFaq = ref(0)
const activeTariff = ref(0)

const faqs = [
  {
    question: 'Что такое коучинг и с чем вы помогаете?',
    answer: 'Помогаю разобраться в мыслях, чувствах и внутренних конфликтах, лучше понять себя и свои желания, принять решения и перейти от размышлений к конкретным действиям.'
  },
  {
    question: 'На чём вы специализируетесь?',
    answer: 'На самоопределении, принятии решений, личных границах, самооценке, внутренних сомнениях, повторяющихся сценариях и ситуациях, когда человек понимает проблему, но не знает, как её изменить.'
  },
  {
    question: 'С какими запросами можно прийти?',
    answer: 'Например: «Не понимаю, чего хочу», «Не могу принять решение», «Постоянно сомневаюсь в себе», «Боюсь перемен», «Не могу выйти из отношений/ситуации», «Хочу изменить жизнь, но не знаю с чего начать».'
  },
  {
    question: 'Как проходит встреча?',
    answer: 'Мы разбираем ваш запрос через диалог и вопросы, исследуем мысли, чувства и убеждения, которые влияют на ситуацию, и вместе приходим к более ясному пониманию того, что происходит и какие шаги вы хотите предпринять.'
  },
  {
    question: 'Нужно ли заранее знать, с чем я хочу работать?',
    answer: 'Нет. Можно прийти даже с ощущением: «Я не понимаю, что со мной происходит». Вместе сформулируем запрос уже в процессе.'
  },
  {
    question: 'Сколько встреч мне понадобится?',
    answer: 'Зависит от запроса. Иногда достаточно одной встречи, чтобы разобраться в конкретной ситуации, а более глубокая работа может потребовать нескольких встреч.'
  },
  {
    question: 'Чем коучинг отличается от психотерапии?',
    answer: 'Коучинг сфокусирован прежде всего на осознании текущей ситуации, целях, выборе и дальнейших действиях. Если запрос связан с психическим расстройством, травмой или состоянием, требующим медицинской/психотерапевтической помощи, коучинг не заменяет специалиста соответствующего профиля.'
  },
  {
    question: 'Можно ли прийти с конкретной проблемой?',
    answer: 'Да. Не обязательно заниматься собой «в целом» — можно разобрать конкретную ситуацию, решение, конфликт или вопрос, который сейчас занимает ваши мысли.'
  },
  {
    question: 'Что я получу после встречи?',
    answer: 'Больше ясности относительно своей ситуации, понимание собственных желаний и мотивов, возможных ограничений и конкретных следующих шагов.'
  },
  {
    question: 'Онлайн или офлайн?',
    answer: 'Онлайн-встречи проходят в удобном для вас формате видеосвязи.'
  }
]

const tariffs = [
  {
    meetings: '1',
    title: 'ПЕРВАЯ ВСТРЕЧА',
    price: '1.000 ₽',
    discount: '50%',
    saving: '1.000 ₽',
    total: '1.000 ₽',
    oldTotal: '2.000 ₽'
  },

  {
    meetings: '5',
    title: '5 ВСТРЕЧ',
    price: '1.000 ₽',
    discount: '50%',
    saving: '1.000 ₽',
    total: '5.000 ₽',
    oldTotal: '10.000 ₽'
  },

  {
    meetings: '10',
    title: '10 ВСТРЕЧ',
    price: '750 ₽',
    discount: '62,5%',
    saving: '1.250 ₽',
    total: '7.500 ₽',
    oldTotal: '20.000 ₽'
  },

  {
    meetings: '20',
    title: '20 ВСТРЕЧ',
    price: '500 ₽',
    discount: '75%',
    saving: '1.500 ₽',
    total: '10.000 ₽',
    oldTotal: '40.000 ₽'
  }
]

const nextTariff = () => {
  if (activeTariff.value < tariffs.length - 1) {
    activeTariff.value++
  }
}

const prevTariff = () => {
  if (activeTariff.value > 0) {
    activeTariff.value--
  }
}

const toggleFaq = (index) => {
  activeFaq.value = activeFaq.value === index ? -1 : index
}

let observer

onMounted(() => {
  observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add('is-visible')
        observer.unobserve(entry.target)
      }
    })
  }, { threshold: 0.12 })

  document.querySelectorAll('.reveal').forEach((el) => observer.observe(el))
})

onBeforeUnmount(() => observer?.disconnect())
</script>

<template>
  <div class="site">
    <header class="header reveal">
      <div class="brand">
        <div class="brand__name">Воробьев Никита</div>
        <div class="brand__subtitle">Психологическая помощь</div>
      </div>
    </header>

    <main>
      <section id="about" class="section about reveal">
        <h1>Обо мне</h1>

        <div class="about__content">
          <p>Привет. Я помогу тебе увидеть в себе то, что когда-то оказалось глубоко спрятано — мысли, чувства и стороны личности, о которых ты, возможно, уже давно забыл.</p>
          <p>Через меня прошли десятки людей. У каждого была своя история, свои страхи, желания и внутренние противоречия. И далеко не каждый способен заметить то, что скрывается за обычными словами и поведением.</p>
          <p>Я хорошо разбираюсь в людях. Замечаю детали, которые обычно остаются незаметными, чувствую противоречия и умею заглянуть немного глубже привычного образа человека.</p>
          <p>Здесь не будет поверхностных советов и банальных фраз вроде «просто отпусти».</p>
          <p>Здесь мы будем разбирать тебя настоящего.</p>
          <p>Возможно, ты узнаешь о себе то, чего не замечал годами.<br>И, возможно, вспомнишь ту часть себя, которую когда-то пришлось спрятать.</p>
        </div>
      </section>

      <section id="tariffs" class="section tariffs reveal">
        <h2>Тарифы сеансов</h2>

        <div class="tariff-slider">

          <!-- Кнопка назад -->
          <button
            class="slider-arrow"
            type="button"
            aria-label="Предыдущий тариф"
            @click="prevTariff"
          >
            ←
          </button>

          <!-- Окно слайдера -->
          <div class="tariffs-window">
            <div
              class="tariffs-track"
              :style="{
                transform: `translateX(-${activeTariff * 100}%)`
              }"
            >
              <article
                v-for="tariff in tariffs"
                :key="tariff.meetings"
                class="tariff-card"
              >
                <div class="tariff-card__top">
                  <span class="tariff-number">
                    {{ tariff.meetings }}
                  </span>

                  <h3>{{ tariff.title }}</h3>
                </div>

                <div class="tariff-table">

                  <div class="tariff-row tariff-row--head">
                    <span>Цена за 1</span>
                    <span>Скидка</span>
                    <span>Экономия</span>
                  </div>

                  <div class="tariff-row">
                    <strong>{{ tariff.price }}</strong>
                    <strong>{{ tariff.discount }}</strong>
                    <strong>{{ tariff.saving }}</strong>
                  </div>

                </div>

                <div class="tariff-total">
                  <span>Итого</span>

                  <div>
                    <strong>{{ tariff.total }}</strong>
                    <del>{{ tariff.oldTotal }}</del>
                  </div>
                </div>

                <p class="tariff-saving">
                  Экономия по сравнению с базовой ценой:
                  {{ tariff.saving }} за 1 встречу
                </p>
              </article>
            </div>
          </div>

          <!-- Кнопка вперед -->
          <button
            class="slider-arrow"
            type="button"
            aria-label="Следующий тариф"
            @click="nextTariff"
          >
            →
          </button>

        </div>

        <!-- Индикаторы -->
        <div class="tariff-dots">
          <button
            v-for="tariff in tariffs"
            :key="tariff.meetings"
            type="button"
            :class="{ active: activeTariff === tariffs.indexOf(tariff) }"
            :aria-label="`Тариф ${tariff.meetings} встреч`"
            @click="activeTariff = tariffs.indexOf(tariff)"
          ></button>
        </div>

        <div class="tariff-note">
          Базовая цена одной встречи — 2.000 ₽.<br>
          Первая встреча — со скидкой 50%.
        </div>

        <a
          class="booking-button"
          href="#contacts"
        >
          Записаться
        </a>
      </section>

      <section id="faq" class="section faq reveal">
        <h2>Частые вопросы?</h2>

        <div class="faq-list">
          <div v-for="(item, index) in faqs" :key="item.question" class="faq-item">
            <button class="faq-question" @click="toggleFaq(index)" :aria-expanded="activeFaq === index">
              <span class="faq-marker">&gt;</span>
              <span>{{ item.question }}</span>
              <span class="faq-plus">{{ activeFaq === index ? '−' : '+' }}</span>
            </button>

            <div class="faq-answer" :class="{ open: activeFaq === index }">
              <div class="faq-answer__inner">
                <p>{{ item.answer }}</p>
              </div>
            </div>
          </div>
        </div>
      </section>
    </main>

    <footer id="contacts" class="footer reveal">
      <h2>Социальные сети</h2>

      <div class="footer__links">
        <a href="https://t.me/h010dok" target="_blank" rel="noopener noreferrer">ТГК:</a>
        <div class="contact-row">
          <a href="tel:+79605472151">Контакт:</a>
          <span>+7(960)547-21-51</span>
        </div>
        <a href="https://t.me/h010dok" target="_blank" rel="noopener noreferrer">@h010dok</a>
        <a class="rules" href="#rules" @click.prevent>Правила пользования сайтом</a>
      </div>
    </footer>
  </div>
</template>
