#pragma once
#include "headers.h"
#include <stdbool.h>
#include <stdlib.h>

// Forward declaration of the struct
struct rr_node;

// Define RR_Node
typedef struct rr_node {
    Process* data;
    struct rr_node* next;
} RR_Node;

// Define RR_Queue
typedef struct rr_queue {
    RR_Node* start;
    RR_Node* rear;
    void (*insert)(struct rr_queue*, RR_Node*);  // Corrected function pointer type
    RR_Node* (*dequeue)(struct rr_queue*);
    bool (*is_empty)(struct rr_queue*);
    RR_Node* (*peek)(struct rr_queue*);
} RR_Queue;

// Function Implementations
void insert_fun_rr(RR_Queue* q, RR_Node* toinsert) {  // Corrected parameter types
    if (q->rear == NULL) {
        q->start = q->rear = toinsert;
        return;
    }
    q->rear->next = toinsert;
    q->rear = toinsert;
}

RR_Node* dequeue_fun_rr(RR_Queue* q) {
    if (q->start == NULL) {
        return NULL;
    }

    RR_Node* temp = q->start;
    q->start = temp->next;

    if (q->start == NULL) {
        q->rear = NULL;
    }

    return temp;
}

bool is_empty_fun_rr(RR_Queue* q) {
    return (q->start == NULL);
}

RR_Node* peek_queue_rr(RR_Queue* q)
{
    if (q->start == NULL) {
        return NULL;
    }

    RR_Node* temp = q->start;

    return temp;
}

// Global Variable
RR_Queue default_rr_queue;

// Initialization Function
static void create_default_rr_q(RR_Queue* queue) {
    queue->start = queue->rear = NULL;
    queue->insert = &insert_fun_rr;
    queue->dequeue = &dequeue_fun_rr;
    queue->is_empty = &is_empty_fun_rr;
    queue->peek = &peek_queue_rr;
}